## 🧩 Phrase TMS ↔ GitHub Automation Workflow (SUSE Linux Enterprise Smart Docs)

[![Sync from Client Repo](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/sync-from-client-repo.yml/badge.svg)](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/sync-from-client-repo.yml)

[![DocBook Preprocess](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/preprocess.yml/badge.svg)](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/preprocess.yml)

[![Process Phrase Incoming Files](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/pull-from-phrase-incoming.yml/badge.svg)](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/pull-from-phrase-incoming.yml)

[![DocBook Postprocess](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/postprocess.yml/badge.svg)](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/postprocess.yml)

[![Sync to Client Repo](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/sync-to-client-repo.yml/badge.svg)](https://github.com/eoinmurphy-vt/suse.sle.phrase.automation.test/actions/workflows/sync-to-client-repo.yml)

### 🔄 Overview

This repository is integrated with **Phrase TMS** to automate the translation lifecycle of
**DocBook 5.2 XML** files (topics, snippets and `.asm.xml` assemblies) and the localizable
**entity files** (`l10n-*.ent`).

---

### 🚦 Automation Status

The badges above show the current automation state for each workflow action:

| Status         | Meaning                                                                    |
| -------------- | -------------------------------------------------------------------------- |
| 🟢 **Passing** | The most recent run completed successfully                                 |
| 🔴 **Failing** | The workflow encountered an error — check the *Actions* tab for logs       |

---

### 📄 Which files are translated

| File                         | Sent to Phrase TMS | Notes                                                              |
| ---------------------------- | ------------------ | ------------------------------------------------------------------ |
| `*.xml` (incl. `*.asm.xml`)  | Yes                | Imported with the XML (XPath) file import settings of the template |
| `l10n-*.ent`                 | Yes                | Imported by the Phrase TMS custom file type `l10n-.*\.ent` (TXT)   |
| `schemas.xml`                | No                 | Editor schema locations, nothing to translate                      |
| Any other `*.ent`            | No                 | For example `generic-entities.ent`: product names, not translated  |
| Images and all other files   | No                 | Not synced                                                         |

---

### 🧠 Automation Logic

1. **Sync Stage** (`sync-from-client-repo.yml`)

   * Copies `*.xml` and `l10n-*.ent` from the client repository into `source/<client-id>/`

2. **Preprocessing Stage** (`preprocess.yml`, `preprocess_xml.py`)

   * Trigger: when the sync workflow completes
   * Converts files to UTF-8 with Unix LF newlines
   * Leaves out the files that are not translated (see the table above)
   * Logs a warning if an XML file is not well-formed, or if an `.ent` file contains a line
     that Phrase TMS would not import (anything other than a single-line `<!ENTITY name "value">`)
   * Protects entity references inside attribute values, because Phrase TMS drops them:

     ```xml
     <productname version="&productnumber;">   →   <productname version="{{ent:productnumber}}">
     ```
   * Nothing else is changed: tabs, spaces and entity references in text are left exactly as they are
   * Saves results in `processed/` for Phrase TMS to pull

3. **Translation Stage (in Phrase TMS)**

   * Phrase TMS syncs the `processed/` folder as the **source**
   * When translation is complete, Phrase TMS pushes the files to the `translated/` folder on the
     `phrase-incoming` branch, and `pull-from-phrase-incoming.yml` copies them to `main`

4. **Postprocessing Stage** (`postprocess.yml`, `postprocess_xml.py`)

   * Trigger: manual (*Actions* tab)
   * Converts files to UTF-8 with Unix LF newlines
   * Restores the protected entity references: `{{ent:productnumber}}` → `&productnumber;`
   * Makes the XML declaration match the English source. Phrase TMS adds
     `<?xml version='1.0' encoding='UTF-8'?>` to files that have no declaration; it is removed again
   * Sets `xml:lang` to the target language, for example `xml:lang="en"` → `xml:lang="de"`
     (switch off with the variable `SET_XML_LANG` = `false`)
   * **Does not deliver** a file that is broken: XML that is no longer well-formed, or an `.ent` file
     whose `<!ENTITY …>` lines or entity names were damaged. The run is marked as failed and the
     file is named in the log; all other files are still written
   * Logs a warning if the DOCTYPE or the entity references (`&productname;` …) differ from the
     English file in `processed/`
   * Writes the final files into `final/<client-id>/<language>/`

5. **Delivery Stage** (`sync-to-client-repo.yml`)

   * Trigger: manual
   * Opens a pull request in the client repository with the contents of `final/<client-id>/`

---

### ⚙️ Folder Structure

| Folder                  | Purpose                                                                        |
| ----------------------- | ------------------------------------------------------------------------------ |
| **`source/`**           | Original English files copied from the client repository                       |
| **`processed/`**        | UTF-8 files prepared for Phrase TMS                                            |
| **`phrase-incoming`**   | Branch where Phrase TMS commits completed translations                         |
| **`translated/`**       | Folder where GitHub commits completed translations from phrase-incoming branch |
| **`final/`**            | Final checked files, ready for delivery                                        |

Path mapping:

    client repo   <watch_path>/tasks/example.xml
    source/       source/<client-id>/tasks/example.xml
    processed/    processed/<client-id>/tasks/example.xml
    translated/   translated/<phrase-locale>/<client-id>/tasks/example.xml      (e.g. de_de)
    final/        final/<client-id>/<language>/tasks/example.xml                (e.g. de)
    client repo   <target_path>/<language>/tasks/example.xml

The language folder is the 2-letter language code of the Phrase TMS locale (`de_de` → `de`,
`pt_br` → `pt`, `zh_cn` → `zh`). Exceptions are defined in `get_target_lang()` in `postprocess_xml.py`;
add one if two locales of the same language are ever translated, or both are delivered to one folder.

---

### 📂 Repository Structure

    ├── source/                    # Source English files
    ├── processed/                 # Pre-processed English files
    ├── translated/                # Translated files
    ├── final/                     # Post-processed translated files
    ├── logs/                      # Execution logs
    ├── .github/
    │   └── workflows/
    │       ├── sync-from-client-repo.yml        # Scheduled / manual
    │       ├── preprocess.yml                   # Runs after the sync workflow
    │       ├── pull-from-phrase-incoming.yml    # Triggered on push to phrase-incoming
    │       ├── postprocess.yml                  # Manual
    │       └── sync-to-client-repo.yml          # Manual
    ├── preprocess_xml.py          # Prepares files for Phrase TMS
    ├── postprocess_xml.py         # Checks and finalizes translated files
    └── l10n_common.py             # Shared checks used by both scripts

---

### ⚙️ Configuration & Admin Guide

This workflow uses GitHub Actions Variables to manage repository connections and folder paths. This allows administrators to change configuration (like switching to a new target repository or changing folder names) without editing any code.

1. **How to Change Settings**

   * Navigate to the main page of this repository.
   * Click the Settings tab in the top navigation bar.
   * In the left sidebar, locate the Security section and Secrets and variables.
   * Click Actions.
   * Select the Variables tab (ensure you are not on the "Secrets" tab).
   * To change a setting, click the pencil icon (Edit) next to the variable.
   * To add a missing setting, click New repository variable.

2. **Available Variables**

If these variables are not set, the workflow will use the Default Values listed below.

| Variable Name                   | Default Value       | Description                                                                                         |
| ------------------------------- | ------------------- | --------------------------------------------------------------------------------------------------- |
| **`CONTENT_DIR`**               | source              | The local folder where the English files are stored.                                                |
| **`TRANSLATED_DIR`**            | translated          | The folder where Phrase TMS pushes translated files.                                                |
| **`FINAL_DIR`**                 | final               | The folder where the final files are saved.                                                         |
| **`SET_XML_LANG`**              | true                | Set to `false` to leave `xml:lang="en"` unchanged in translated files.                              |
| **`CURRENT_REPO_NAME`**         | (Your Repo)         | The owner/repo string of this repository (e.g., my-org/docs-connector). Used for dispatch triggers. |
| **`SUSE_CLIENT_CONFIGURATION`** | (JSON content)      | The configuration settings used to connect to client repos (see below).                             |

3. **Required Secrets**

| Secret Name                        | Used for                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------- |
| **`VISTATEC_REPO_WRITE_PAT`**      | Pushing synced and postprocessed files to this repository                   |
| **`VISTATEC_REPO_TRIGGER_PAT`**    | Copying translations from the `phrase-incoming` branch to `main`            |
| **`SUSE_PHRASE_CLIENT_WRITE_PAT`** | Reading the client repository and opening the delivery pull request there   |

**Example: `SUSE_CLIENT_CONFIGURATION`**

This variable contains the client‑specific repository configuration as a **JSON array**. Each object in the array is one configuration. Add more objects to connect to more repositories and/or directory locations.

```json
[
  {
    "id": "sle-smart-docs",
    "url": "client-org/client-repo",
    "branch": "main",
    "schedule": "daily",
    "watch_path": "en/",
    "target_path": "l10n/",
    "exclude_paths": ""
  }
]
```

**Field Descriptions**

| Field             | Meaning                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| **id**            | Unique identifier for the client configuration (Use kebab case, e.g., this-is-kebab-case).         |
| **url**           | GitHub repository path in `owner/repo` format.                                                     |
| **branch**        | The branch monitored for updates.                                                                  |
| **schedule**      | How often this repo should be pulled (`hourly`, `daily`, `monthly`).                               |
| **watch\_path**   | Path within the client repo to watch for changes (end it with `/`).                                |
| **target\_path**  | Path in the client repo where the language folders are delivered.                                  |
| **exclude_paths** | List of files and folders to exclude (separated by space). Use empty string `""` for no exclusions |

---

### 👥 For Project Managers

* New or changed `.xml` and `l10n-*.ent` files in the **`watch_path`** of the client repository are picked up by the `Sync Changes from External Repos` action and copied to **`source/`**.
* Phrase TMS automatically detects and imports them from the **`processed/`** folder.
* Once translations are complete, the **`translated/`** folder is updated automatically.
* Run `Postprocess Translated Files` from the *Actions* tab. The **`final/`** folder then contains the checked files. If the run is red, open its log: it names every file that was not delivered and why.
* Run `Sync Changes to External Repos` to open the delivery pull request in the client repository.

---

### ⚠️ Important Limitations

   While most settings are configurable via the Variables UI, specific GitHub architecture limitations require the following to be changed manually in the YML files if updated:
   * Schedules: The sync frequency (e.g., */15 * * * *) must be edited in .github/workflows/sync-from-client-repo.yml.
   * File types: The file patterns that are synced (`*.xml`, `l10n-*.ent`) are set in sync-from-client-repo.yml and in `l10n_common.py`.
   * `preprocess_xml.py` always reads from `source/` and writes to `processed/`.
   * Files deleted in the client repository are not removed from `processed/`, `translated/` or `final/`.

---

### 🧩 Technical Notes

* Stages run via [GitHub Actions](https://github.com/features/actions).
* Scripts used:

  * `preprocess_xml.py`
  * `postprocess_xml.py`
  * `l10n_common.py`
* Encoding: **Unix-compatible UTF-8**
* The XML files load their entities from `../common/generic-entities.ent`. That file is not translated and not delivered by this pipeline; the client repository must provide it next to each language's files.

---

### <img src="assets/phrase_icon.png" width="24" style="position: relative; top: 8px;" /> Phrase Integration

**Phrase GitHub App**

Install the `Phrase GitHub App` on your GitHub repository to enable sending files to Phrase TMS.

   * [Phrase GitHub App](https://github.com/apps/phrase-app-connector-eu)

**Connector**

In Phrase TMS set up a `Connector` to link to your GitHub repository.

   * Configure the pull request branch and the folder used for import/export.

**Custom file type**

In Phrase TMS, under Settings → Custom file types:

   * `l10n-.*\.ent`, file type TXT, importing only the quoted value of each `<!ENTITY name "value">` line

**Project templates**

In Phrase TMS, configure `Project templates`.

   * Each language requires its own project template
   * Configure file import settings: file type **Auto-detect** (so the `.ent` custom file type applies) and the XML settings in **XPath** mode
   * Configure the machine translation engine
   * Configure pre-translation rules
   * Configure project status automation
   * Define completed file naming and export paths
   * Configure optional settings such as Analysis and Workflow

**Automated project creation**

In Phrase TMS set up `Automated project creation` templates.

   * Each language requires its own automation template
   * Select the project template to use
   * Configure export rules
   * Define the remote folder (`processed/`) and file types (`xml`, `ent`) that trigger automations
   * Configure trigger monitors (scheduled or webhook-based)
   * Configure any additional project actions

**Phrase Orchestrator**

In Phrase Orchestrator, set up a `Workflow`.

   * Add a filter to the workflow for each project template
   * The workflow is used to save completed translations to the project TM

---

### 📝 License

This project is licensed under the Apache 2.0 License. © 2026 Vistatec, Ltd.

---
