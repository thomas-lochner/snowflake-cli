# v2.0.0

## Backward incompatibility
* In `snowpark function` command:
  * Combined options `--function` and `--input-parameters` to `identifier` argument.
  * Changed name of option from `--return-type` to `returns`.
* In `snowpark procedure` command:
  * Combined options `--procedure` and `--input-parameters` to `identifier` argument.
  * Changed name of option from `--return-type` to `--returns`.
* In `snowpark procedure coverage` command:
  * Combined options `--name` and `--input-parameters` to `identifier` argument.
* Changed path to coverage reports on stage, previously created procedures with coverage will not work, have to be recreated.
* Update function or procedure will upload function/procedure code to new path on stage. Previous code will remain under old path on stage.
* Snowpark command `compute-pool` and its alias `cp` were replaced by `pool` command.
* `snow snowpark registry` was replaced with `snow registry` command.
* Removed `snow streamlit create` command. Streamlit can be deployd using `snow streamlit deploy`
* `snow connection test` now outputs all connection details (except for the password), along with connection status

## New additions
* `--temporary-connection` flag, that allows you to connect, without anything declared in config file
* `snow streamlit init` command that creates a new streamlit project.
* `snow streamlit deploy` support pages and environment.yml files.

## Fixes and improvements
* Adjust streamlit commands to PuPr syntax

# v1.1.1

## Backward incompatibility
* Removed short version `-p` of `--password` option.

## New additions
* Added commands:
  * `snow snowpark registry list-images`
  * `snow snowpark registry list-tags`

## Fixes and improvements
* Too long texts in table cells are now wrapped instead of cropped
* Split global options into separate section in `help`
* Avoiding unnecessary replace in function/procedure update
* Added global options to all commands
* Updated help messages
* Fixed problem with Windows shortened paths
* If only one connection is configured, will be used as default
* Fixed registry token connection issues
* Fixes in commands belonging to `snow snowpark compute-pool` and `snow snowpark services` groups
* Removed duplicated short option names in a few commands by:
  * Removing `-p` short option for `--password` option for all commands (backward incompatibility affecting all the commands using a connection) (it was conflicting with various options in a few commands)
  * Removing `-a` short option for `--replace-always` in `snow snowpark function update` command (it was conflicting with short version of `--check-anaconda-for-pypi-deps`)
  * Removing `-c` short option for `--compute-pool` in `snow snowpark jobs create` (it was conflicting with short version of global `--connection` option)
  * Removing `-c` short option for `--container-name` in `snow snowpark jobs logs` (it was conflicting with short version of global `--connection` option)
* Fixed parsing of specs yaml in `snow snowpark services create` command