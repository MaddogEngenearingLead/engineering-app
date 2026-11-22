# About dialog

The desktop application's **Help → About** menu identifies the installed build for testers. It displays the application name, version, build date, MaddDog Systems branding, and GitHub repository name.

## Metadata source

All user-facing application identity and release metadata is centralized in `app/version.py`:

- `APP_NAME`
- `__version__`
- `__build_date__`
- `PUBLISHER`
- `REPOSITORY_NAME`

The release workflow stamps the tagged version (for tagged releases) and the UTC build date into that module before creating the packaged application. The GUI reads the same values, so the About dialog and window title cannot drift from the configured release metadata. For local source runs the checked-in version and date are shown.

## Finding build information

Launch the desktop app and choose **Help → About**. The build date uses ISO `YYYY-MM-DD` format. Compare the displayed version and date when reporting an issue or confirming which build a tester is running.
