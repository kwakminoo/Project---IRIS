import { ContainerModule } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { IrisBridgeContribution } from './iris-bridge-contribution';

export default new ContainerModule(bind => {
    bind(IrisBridgeContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisBridgeContribution);
});
