import { ContainerModule } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { IrisProductContribution } from './iris-product-contribution';

export default new ContainerModule(bind => {
    bind(IrisProductContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisProductContribution);
});
