# addonfactory-test-matrix-action

This Github Actions is used to prepare output variables that can be used to determine the correct flow of a CI workflow. 

Using this approach an addon/connector to be tested can identify by feature flag which versions of Splunk should be tested. The tool is configured by a `.addonmatrix` file in the repo root. If no file is present all supported versions of Splunk will be tested.

Using the current Support Policy Expiration dates versions of Splunk will be automatically removed and added in the future.

The following example configuration file indicates a version of Splunk with "METRICS_MULTI" is required.

```
--splunkfeatures METRICS_MULTI
```
