# addonfactory-test-matrix-action

This GitHub Actions is used to prepare output variables that can be used to determine the correct flow of a CI workflow. 

Using this approach an add-on/connector to be tested can identify by feature flag which versions of Splunk should be tested.

Using the current Support Policy Expiration dates versions of Splunk will be automatically removed and added in the future.

# Development flow

Once new version of Splunk or SC4S is released and PR with updates in SC4S_matrix.conf or splunk_matrix.conf is created, new configuration should be tested against TAs before the new release of action.

1. Update the [action.yaml](https://github.com/splunk/addonfactory-test-matrix-action/blob/main/action.yml#L6) file - you need to configure it to use the Dockerfile directly. This ensures that the latest changes are included in the testing environment.
2. Create a PR on [addonfactory-workflow-addon-release](https://github.com/splunk/addonfactory-workflow-addon-release)
3. In this PR, modify the matrix step to reference the branch of `addonfactory-test-matrix-action` that is currently under test.
4. Execute CI for several TAs with `build-test-release` workflow referencing created branch on `addonfactory-workflow-addon-release`
5. After successful execution of tests, make a new fix release of `addonfactory-test-matrix-action` which will be automatically incorporated into latest `addonfactory-workflow-addon-release` workflow
6. Backport the changes to older version of `addonfactory-workflow-addon-release` if necessary
7. *Only for changes in the `config/splunk_matrix.conf`: Follow the instructions from [Runbook to creating and publishing docker images used in reusable workflow](https://github.com/splunk/addonfactory-workflow-addon-release/blob/main/runbooks/addonfactory-workflow-addon-release-docker-images.md#runbook-to-publish-multiple-images-of-different-linux-flavors-and-versions-for-scripted-inputs-tests) to create and publish Splunk images for scripted inputs tests based on the updates in the matrix coniguration.
