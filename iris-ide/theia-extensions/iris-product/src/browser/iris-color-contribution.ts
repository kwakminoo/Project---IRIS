import { injectable } from '@theia/core/shared/inversify';
import { ColorContribution } from '@theia/core/lib/browser/color-application-contribution';
import { ColorRegistry } from '@theia/core/lib/browser/color-registry';

const TRANSPARENT = {
    dark: 'rgba(0, 0, 0, 0)',
    light: 'rgba(0, 0, 0, 0)',
    hcDark: 'rgba(0, 0, 0, 0)',
    hcLight: 'rgba(0, 0, 0, 0)',
};

const LAYOUT_TRANSPARENT = {
    dark: 'rgba(0, 0, 0, 0)',
    light: 'rgba(0, 0, 0, 0)',
    hcDark: 'rgba(0, 0, 0, 0)',
    hcLight: 'rgba(0, 0, 0, 0)',
};

/** Activity Bar 배경·보더 투명 — 아이콘만 보이도록 */
@injectable()
export class IrisColorContribution implements ColorContribution {
    registerColors(colors: ColorRegistry): void {
        colors.register({
            id: 'activityBar.background',
            defaults: TRANSPARENT,
            description: 'IRIS embedded IDE — transparent activity bar background',
        });
        colors.register({
            id: 'activityBar.border',
            defaults: TRANSPARENT,
            description: 'IRIS embedded IDE — transparent activity bar border',
        });
        colors.register({
            id: 'activityBar.activeBackground',
            defaults: TRANSPARENT,
            description: 'IRIS embedded IDE — transparent active tab background',
        });
        colors.register({
            id: 'activityBar.inactiveBackground',
            defaults: TRANSPARENT,
            description: 'IRIS embedded IDE — transparent inactive tab background',
        });
        for (let i = 0; i <= 4; i++) {
            colors.register({
                id: `layout.color${i}`,
                defaults: LAYOUT_TRANSPARENT,
                description: `IRIS embedded IDE — transparent layout color ${i}`,
            });
        }
    }
}
