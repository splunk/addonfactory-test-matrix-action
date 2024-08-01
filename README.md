# addonfactory-test-matrix-action

This Github Actions is used to prepare output variables that can be used to determine the correct flow of a CI workflow. 

Using this approach an addon/connector to be tested can identify by feature flag which versions of Splunk should be tested. The tool is configured by a `.addonmatrix` file in the repo root. If no file is present all supported versions of Splunk will be tested.

Using the current Support Policy Expiration dates versions of Splunk will be automatically removed and added in the future.

The following example configuration file indicates a version of Splunk with "METRICS_MULTI" is required.

```
--splunkfeatures METRICS_MULTI
```

# Development flow

Once new version of Splunk or sc4s is released and PR with updates in SC4S_matrix.conf or splunk_matrix.conf is created, new configuration should be tested against TAs before the new release of action. 
1. update the [action.yaml](https://github.com/splunk/addonfactory-test-matrix-action/blob/main/action.yml#L6) file - you need to configure it to use the Dockerfile directly. This ensures that the latest changes are included in the testing environment.
2. Create a PR on [addonfactory-workflow-addon-release](https://github.com/splunk/addonfactory-workflow-addon-release)
3. In this PR, modify the matrix step to reference the branch of `addonfactory-test-matrix-action` that is currently under test.
4. Execute CI for several TAs with `build-test-release` workflow referencing created branch on `addonfactory-workflow-addon-release`
5. After succesfull execution of tests, make a new fix release of `addonfactory-test-matrix-action` which will be automatically incorporated into latest `addonfactory-workflow-addon-release` workflow
