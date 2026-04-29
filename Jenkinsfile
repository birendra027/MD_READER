// ─────────────────────────────────────────────────────────────────────────────
// MD Reader — CI/CD Pipeline
//
// Triggers on every push to the `dev_1.0` branch.
//
// Stages:
//   1. Checkout
//   2. Backend Lint  — pylint on all Python sources
//   3. Frontend CI   — TypeScript type-check + production build
//   4. Build Images  — docker build for backend & frontend
//   5. Push Images   — push to the private registry
//   6. Deploy        — helm upgrade in the md-reader k8s namespace
//   7. Verify        — wait for rollout to complete
//
// Requirements on the Jenkins agent:
//   • docker (with permission to build & push)
//   • kubectl  (kubeconfig must be available — see KUBECONFIG_CREDENTIAL_ID)
//   • helm ≥ 3
//   • python 3.11 + pip  (for pylint; can also run inside a container)
//   • node 20 + npm      (for the frontend type-check)
//
// Credentials (configured in Jenkins → Credentials):
//   REGISTRY_CREDENTIALS  — Username/Password for the Docker registry
//   KUBECONFIG_SECRET     — Secret file containing the kube config
// ─────────────────────────────────────────────────────────────────────────────

pipeline {
    agent any

    // ── Only run on the dev_1.0 branch ───────────────────────────────────────
    triggers {
        githubPush()   // fires on every push; branch filter is in the `when` blocks below
    }

    // ── Global environment ────────────────────────────────────────────────────
    environment {
        // Docker registry — must match the registry used in helm/md-reader/values.yaml
        REGISTRY               = 'host.docker.internal:9001'
        BACKEND_IMAGE          = "${REGISTRY}/md-reader-backend"
        FRONTEND_IMAGE         = "${REGISTRY}/md-reader-frontend"
        IMAGE_TAG              = "${env.BUILD_NUMBER}"          // Jenkins build number used as image tag

        // Helm / k8s
        HELM_RELEASE           = 'md-reader'
        HELM_NAMESPACE         = 'md-reader'
        HELM_CHART             = './helm/md-reader'

        // Jenkins credential IDs
        REGISTRY_CREDENTIALS   = 'admin'   // Docker registry creds
        KUBECONFIG_CREDENTIAL_ID = 'kubeconfig-secret'           // kubeconfig file secret
    }

    // ── Stage selection checkboxes (shown in "Build with Parameters" UI) ────────
    parameters {
        booleanParam(name: 'RUN_BACKEND_LINT',  defaultValue: true,  description: 'Run pylint on backend Python sources')
        booleanParam(name: 'RUN_FRONTEND_CI',   defaultValue: true,  description: 'Run TypeScript type-check and production build')
        booleanParam(name: 'RUN_BUILD_IMAGES',  defaultValue: true,  description: 'Build backend and frontend Docker images')
        booleanParam(name: 'RUN_PUSH_IMAGES',   defaultValue: true,  description: 'Push images to the private registry')
        booleanParam(name: 'RUN_DEPLOY',        defaultValue: true,  description: 'Deploy to Kubernetes via Helm upgrade')
        booleanParam(name: 'RUN_VERIFY',        defaultValue: true,  description: 'Wait for Kubernetes rollout to complete')
    }

    options {
        // Keep only the last 10 builds to save disk space
        buildDiscarder(logRotator(numToKeepStr: '10'))
        // Abort the build if it runs longer than 30 minutes
        timeout(time: 30, unit: 'MINUTES')
        // Do not allow concurrent builds on the same branch
        disableConcurrentBuilds()
        // Add timestamps to every log line
        timestamps()
    }

    stages {

        // ── 1. Checkout ───────────────────────────────────────────────────────
        stage('Checkout') {
            when {
                branch 'dev_1.0'
            }
            steps {
                checkout scm
                echo "Branch: ${env.BRANCH_NAME}  Commit: ${env.GIT_COMMIT}"
            }
        }

        // ── 2. Backend Lint ───────────────────────────────────────────────────
        stage('Backend Lint') {
            when {
                allOf {
                    branch 'dev_1.0'
                    expression { return params.RUN_BACKEND_LINT }
                }
            }
            steps {
                dir('backend') {
                    sh '''
                        python3 -m venv .ci-venv
                        . .ci-venv/bin/activate
                        pip install --quiet pylint
                        pip install --quiet -r requirements.txt
                        pylint \
                            --rcfile=../.pylintrc \
                            --output-format=text \
                            --fail-under=7.0 \
                            main.py \
                            s3_client.py \
                            md_converter.py \
                            parquet_handler.py \
                            ws_handler.py \
                            chatbot/
                    '''
                }
            }
            post {
                always {
                    // Archive pylint output so it's visible in the Jenkins UI
                    archiveArtifacts artifacts: 'backend/.pylint-report.txt', allowEmptyArchive: true
                }
            }
        }

        // ── 3. Frontend CI ────────────────────────────────────────────────────
        stage('Frontend CI') {
            when {
                allOf {
                    branch 'dev_1.0'
                    expression { return params.RUN_FRONTEND_CI }
                }
            }
            steps {
                dir('frontend') {
                    sh '''
                        npm ci --prefer-offline
                        # TypeScript strict type-check (no emit)
                        npx tsc --noEmit
                        # Production build — catches any bundler/import errors
                        npm run build
                    '''
                }
            }
        }

        // ── 4. Build Docker Images ────────────────────────────────────────────
        stage('Build Images') {
            when {
                allOf {
                    branch 'dev_1.0'
                    expression { return params.RUN_BUILD_IMAGES }
                }
            }
            steps {
                script {
                    // Backend — build context is the repo root (Dockerfile lives in backend/)
                    sh """
                        docker build \
                            -f backend/Dockerfile \
                            -t ${BACKEND_IMAGE}:${IMAGE_TAG} \
                            -t ${BACKEND_IMAGE}:latest \
                            .
                    """
                    // Frontend — build context is the frontend/ directory
                    sh """
                        docker build \
                            -f frontend/Dockerfile \
                            -t ${FRONTEND_IMAGE}:${IMAGE_TAG} \
                            -t ${FRONTEND_IMAGE}:latest \
                            ./frontend
                    """
                }
            }
        }

        // ── 5. Push Images ────────────────────────────────────────────────────
        stage('Push Images') {
            when {
                allOf {
                    branch 'dev_1.0'
                    expression { return params.RUN_PUSH_IMAGES }
                }
            }
            steps {
                script {
                    withCredentials([
                        usernamePassword(
                            credentialsId: REGISTRY_CREDENTIALS,
                            usernameVariable: 'REG_USER',
                            passwordVariable: 'REG_PASS'
                        )
                    ]) {
                        sh "echo '${REG_PASS}' | docker login ${REGISTRY} -u '${REG_USER}' --password-stdin"
                        sh "docker push ${BACKEND_IMAGE}:${IMAGE_TAG}"
                        sh "docker push ${BACKEND_IMAGE}:latest"
                        sh "docker push ${FRONTEND_IMAGE}:${IMAGE_TAG}"
                        sh "docker push ${FRONTEND_IMAGE}:latest"
                    }
                }
            }
            post {
                always {
                    // Always log out from the registry
                    sh "docker logout ${REGISTRY} || true"
                }
            }
        }

        // ── 6. Deploy via Helm ────────────────────────────────────────────────
        stage('Deploy') {
            when {
                allOf {
                    branch 'dev_1.0'
                    expression { return params.RUN_DEPLOY }
                }
            }
            steps {
                withCredentials([
                    file(credentialsId: KUBECONFIG_CREDENTIAL_ID, variable: 'KUBECONFIG')
                ]) {
                    sh """
                        helm upgrade ${HELM_RELEASE} ${HELM_CHART} \
                            --namespace  ${HELM_NAMESPACE} \
                            --reuse-values \
                            --set backend.image.tag=${IMAGE_TAG} \
                            --set frontend.image.tag=${IMAGE_TAG} \
                            --atomic \
                            --timeout 5m \
                            --cleanup-on-fail
                    """
                }
            }
        }

        // ── 7. Verify Rollout ─────────────────────────────────────────────────
        stage('Verify') {
            when {
                allOf {
                    branch 'dev_1.0'
                    expression { return params.RUN_VERIFY }
                }
            }
            steps {
                withCredentials([
                    file(credentialsId: KUBECONFIG_CREDENTIAL_ID, variable: 'KUBECONFIG')
                ]) {
                    sh """
                        kubectl rollout status deployment/${HELM_RELEASE}-backend  \
                            -n ${HELM_NAMESPACE} --timeout=3m
                        kubectl rollout status deployment/${HELM_RELEASE}-frontend \
                            -n ${HELM_NAMESPACE} --timeout=3m
                    """
                }
            }
        }
    }

    // ── Post-pipeline notifications ───────────────────────────────────────────
    post {
        success {
            echo "Pipeline succeeded — ${BACKEND_IMAGE}:${IMAGE_TAG} and ${FRONTEND_IMAGE}:${IMAGE_TAG} are live."
        }
        failure {
            echo "Pipeline FAILED on branch ${env.BRANCH_NAME} at commit ${env.GIT_COMMIT}."
        }
        cleanup {
            // Remove local images to keep the agent disk clean
            sh """
                docker rmi ${BACKEND_IMAGE}:${IMAGE_TAG}  || true
                docker rmi ${BACKEND_IMAGE}:latest         || true
                docker rmi ${FRONTEND_IMAGE}:${IMAGE_TAG} || true
                docker rmi ${FRONTEND_IMAGE}:latest        || true
            """
        }
    }
}
