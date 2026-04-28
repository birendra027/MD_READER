/**
 * Broadcast the current tool's content so the ChatBot can use it as context.
 * Call this from any tool page whenever the user's content changes.
 *
 * The Layout component in App.tsx listens for this event and passes the
 * content down to <ChatBot document={...} />.
 */
export function broadcastToolContent(
  content: string,
  toolId: string,
  toolName: string,
): void {
  window.dispatchEvent(
    new CustomEvent<{ content: string; toolId: string; toolName: string }>(
      'md-tool-content',
      { detail: { content, toolId, toolName } },
    ),
  );
}
