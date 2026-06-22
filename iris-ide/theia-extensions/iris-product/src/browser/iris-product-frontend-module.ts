import { ContainerModule } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { ColorContribution } from '@theia/core/lib/browser/color-application-contribution';
import { IrisColorContribution } from './iris-color-contribution';
import { IrisProductContribution } from './iris-product-contribution';

export default new ContainerModule(bind => {
    bind(IrisProductContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisProductContribution);
    bind(IrisColorContribution).toSelf().inSingletonScope();
    bind(ColorContribution).toService(IrisColorContribution);
});
