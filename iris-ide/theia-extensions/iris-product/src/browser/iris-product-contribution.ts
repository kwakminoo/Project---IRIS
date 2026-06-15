import { injectable } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';

/** Iris 다크 테마 토큰을 document root에 주입 */
@injectable()
export class IrisProductContribution implements FrontendApplicationContribution {
    onStart(): void {
        const root = document.documentElement;
        root.style.setProperty('--iris-bg-primary', '#0b1220');
        root.style.setProperty('--iris-bg-secondary', '#0f172a');
        root.style.setProperty('--iris-panel-bg', '#111827');
        root.style.setProperty('--iris-border', '#334155');
        root.style.setProperty('--iris-accent', '#312e81');
        document.body.classList.add('iris-ide-shell');
    }
}
