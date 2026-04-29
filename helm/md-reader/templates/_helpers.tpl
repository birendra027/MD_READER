{{/*
Expand the name of the chart.
*/}}
{{- define "md-reader.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully-qualified app name (≤ 63 chars).
*/}}
{{- define "md-reader.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label.
*/}}
{{- define "md-reader.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "md-reader.labels" -}}
helm.sh/chart: {{ include "md-reader.chart" . }}
{{ include "md-reader.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels (used by Deployments and Services).
*/}}
{{- define "md-reader.selectorLabels" -}}
app.kubernetes.io/name: {{ include "md-reader.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Render a full image reference from a component's image values + the global registry.
- If imageValues.registry is a non-empty string it is used as-is (pins to that registry).
- If imageValues.registry is empty, fall back to global.imageRegistry.
- If both are empty, no registry prefix is added (Docker Hub default).

Usage:
  {{ include "md-reader.image" (dict "imageValues" .Values.backend.image "global" .Values.global) }}
*/}}
{{- define "md-reader.image" -}}
{{- $registry := .imageValues.registry | default .global.imageRegistry }}
{{- $repo     := .imageValues.repository }}
{{- $tag      := .imageValues.tag | default "latest" }}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repo $tag }}
{{- else }}
{{- printf "%s:%s" $repo $tag }}
{{- end }}
{{- end }}

{{/*
Return imagePullSecrets as a YAML list (empty if none configured).
*/}}
{{- define "md-reader.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
  {{- range .Values.global.imagePullSecrets }}
  - name: {{ . }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Service name helpers — these are the DNS names used by other pods.
*/}}
{{- define "md-reader.localstack.serviceName" -}}
{{- include "md-reader.fullname" . }}-localstack
{{- end }}

{{- define "md-reader.ollama.serviceName" -}}
{{- include "md-reader.fullname" . }}-ollama
{{- end }}

{{- define "md-reader.backend.serviceName" -}}
{{- include "md-reader.fullname" . }}-backend
{{- end }}

{{- define "md-reader.frontend.serviceName" -}}
{{- include "md-reader.fullname" . }}-frontend
{{- end }}
