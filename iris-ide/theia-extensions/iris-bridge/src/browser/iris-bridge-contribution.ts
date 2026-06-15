import { injectable, inject } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { EditorManager } from '@theia/editor/lib/browser/editor-manager';
import { WorkspaceService } from '@theia/workspace/lib/browser/workspace-service';

interface IrisContextPayload {
    type: 'context.update';
    workspace_path: string;
    active_file_uri: string;
    active_file_language: string;
    selected_text: string;
    selection_range: Record<string, unknown>;
    dirty_state: boolean;
}

@injectable()
export class IrisBridgeContribution implements FrontendApplicationContribution {
    @inject(EditorManager) protected readonly editorManager!: EditorManager;
    @inject(WorkspaceService) protected readonly workspaceService!: WorkspaceService;

    private bridgeBase = 'http://127.0.0.1:3200';
    private pollTimer: ReturnType<typeof setInterval> | undefined;

    onStart(): void {
        const params = new URLSearchParams(window.location.search);
        const port = params.get('irisBridgePort');
        if (port) {
            this.bridgeBase = `http://127.0.0.1:${port}`;
        } else if ((window as unknown as { __IRIS_BRIDGE_URL__?: string }).__IRIS_BRIDGE_URL__) {
            this.bridgeBase = (window as unknown as { __IRIS_BRIDGE_URL__: string }).__IRIS_BRIDGE_URL__;
        }
        this.editorManager.onCurrentEditorChanged(() => this.pushContext());
        this.pollTimer = setInterval(() => this.pullCommands(), 1500);
        this.pushContext();
    }

  onStop(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
  }

    protected async pushContext(): Promise<void> {
        const editor = this.editorManager.currentEditor;
        const uri = editor?.editor.uri.toString() ?? '';
        const selection = editor?.editor.selection ?? undefined;
        const selectedText = selection ? editor?.editor.getSelectedText() ?? '' : '';
        const payload: IrisContextPayload = {
            type: 'context.update',
            workspace_path: this.workspaceService.workspace?.resource?.toString() ?? '',
            active_file_uri: uri,
            active_file_language: editor?.editor.document.languageId ?? '',
            selected_text: selectedText,
            selection_range: selection ? { start: selection.start, end: selection.end } : {},
            dirty_state: editor?.editor.document.dirty ?? false,
        };
        try {
            await fetch(`${this.bridgeBase}/context`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } catch {
            // Iris bridge 미가동 시 무시
        }
    }

    protected async pullCommands(): Promise<void> {
        try {
            const res = await fetch(`${this.bridgeBase}/commands`);
            if (!res.ok) {
                return;
            }
            const data = await res.json() as { commands?: Array<Record<string, unknown>> };
            for (const cmd of data.commands ?? []) {
                await this.handleCommand(cmd);
            }
        } catch {
            // ignore
        }
    }

    protected async handleCommand(cmd: Record<string, unknown>): Promise<void> {
        if (cmd.type === 'editor.open' && typeof cmd.uri === 'string') {
            await this.editorManager.open(new (await import('@theia/core/lib/common/uri')).URI(cmd.uri));
        }
    }
}
