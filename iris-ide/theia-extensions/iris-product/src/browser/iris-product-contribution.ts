import { injectable } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import './iris-transparent-shell.css';

const ACTIVITY_BAR_VARS: Record<string, string> = {
    '--theia-activityBar-background': 'rgba(0, 0, 0, 0)',
    '--theia-activityBar-border': 'rgba(0, 0, 0, 0)',
    '--theia-activityBar-activeBackground': 'rgba(0, 0, 0, 0)',
    '--theia-activityBar-inactiveBackground': 'rgba(0, 0, 0, 0)',
    '--theia-layout-color0': 'rgba(0, 0, 0, 0)',
    '--theia-layout-color1': 'rgba(0, 0, 0, 0)',
    '--theia-layout-color2': 'rgba(0, 0, 0, 0)',
    '--theia-layout-color3': 'rgba(0, 0, 0, 0)',
    '--theia-layout-color4': 'rgba(0, 0, 0, 0)',
};

/** Iris 다크 테마 토큰 + Activity Bar 투명화 */
@injectable()
export class IrisProductContribution implements FrontendApplicationContribution {
    onStart(): void {
        const root = document.documentElement;
        root.style.setProperty('--iris-bg-primary', '#0b1220');
        root.style.setProperty('--iris-bg-secondary', '#0f172a');
        root.style.setProperty('--iris-panel-bg', '#111827');
        root.style.setProperty('--iris-border', '#334155');
        root.style.setProperty('--iris-accent', '#312e81');
        for (const [key, value] of Object.entries(ACTIVITY_BAR_VARS)) {
            root.style.setProperty(key, value);
        }
        document.body.classList.add('iris-ide-shell');
    }
}
