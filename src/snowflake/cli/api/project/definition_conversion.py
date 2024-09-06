from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from click import ClickException
from snowflake.cli._plugins.nativeapp.artifacts import (
    build_bundle,
)
from snowflake.cli._plugins.snowpark.common import is_name_a_templated_one
from snowflake.cli.api.constants import (
    DEFAULT_ENV_FILE,
    DEFAULT_PAGES_DIR,
    PROJECT_TEMPLATE_VARIABLE_OPENING,
    SNOWPARK_SHARED_MIXIN,
)
from snowflake.cli.api.project.schemas.native_app.application import Application
from snowflake.cli.api.project.schemas.native_app.native_app import NativeApp
from snowflake.cli.api.project.schemas.native_app.package import Package
from snowflake.cli.api.project.schemas.project_definition import (
    ProjectDefinition,
    ProjectDefinitionV2,
)
from snowflake.cli.api.project.schemas.snowpark.callable import (
    FunctionSchema,
    ProcedureSchema,
)
from snowflake.cli.api.project.schemas.snowpark.snowpark import Snowpark
from snowflake.cli.api.project.schemas.streamlit.streamlit import Streamlit

log = logging.getLogger(__name__)


def convert_project_definition_to_v2(
    project_root: Path, pd: ProjectDefinition, accept_templates: bool = False
) -> ProjectDefinitionV2:
    _check_if_project_definition_meets_requirements(pd, accept_templates)

    snowpark_data = convert_snowpark_to_v2_data(pd.snowpark) if pd.snowpark else {}
    streamlit_data = convert_streamlit_to_v2_data(pd.streamlit) if pd.streamlit else {}
    native_app_data = (
        convert_native_app_to_v2_data(project_root, pd.native_app)
        if pd.native_app
        else {}
    )
    envs = convert_envs_to_v2(pd)

    data = {
        "definition_version": "2",
        "entities": get_list_of_all_entities(
            snowpark_data.get("entities", {}),
            streamlit_data.get("entities", {}),
            native_app_data.get("entities", {}),
        ),
        "mixins": snowpark_data.get("mixins", None),
        "env": envs,
    }

    return ProjectDefinitionV2(**data)


def convert_snowpark_to_v2_data(snowpark: Snowpark) -> Dict[str, Any]:
    artifact_mapping = {"src": snowpark.src}
    if snowpark.project_name:
        artifact_mapping["dest"] = snowpark.project_name

    data: dict = {
        "mixins": {
            SNOWPARK_SHARED_MIXIN: {
                "stage": snowpark.stage_name,
                "artifacts": [artifact_mapping],
            }
        },
        "entities": {},
    }

    for index, entity in enumerate([*snowpark.procedures, *snowpark.functions]):
        identifier = {"name": entity.name}
        if entity.database is not None:
            identifier["database"] = entity.database
        if entity.schema_name is not None:
            identifier["schema"] = entity.schema_name

        entity_name = (
            f"snowpark_entity_{index}"
            if is_name_a_templated_one(entity.name)
            else entity.name
        )

        if entity_name in data["entities"]:
            raise ClickException(
                f"Entity with name {entity_name} seems to be duplicated. Please rename it and try again."
            )

        v2_entity = {
            "type": "function" if isinstance(entity, FunctionSchema) else "procedure",
            "stage": snowpark.stage_name,
            "handler": entity.handler,
            "returns": entity.returns,
            "signature": entity.signature,
            "runtime": entity.runtime,
            "external_access_integrations": entity.external_access_integrations,
            "secrets": entity.secrets,
            "imports": entity.imports,
            "identifier": identifier,
            "meta": {"use_mixins": [SNOWPARK_SHARED_MIXIN]},
        }
        if isinstance(entity, ProcedureSchema):
            v2_entity["execute_as_caller"] = entity.execute_as_caller

        data["entities"][entity_name] = v2_entity

    return data


def convert_streamlit_to_v2_data(streamlit: Streamlit) -> Dict[str, Any]:
    # Process env file and pages dir
    environment_file = _process_streamlit_files(streamlit.env_file, "environment")
    pages_dir = _process_streamlit_files(streamlit.pages_dir, "pages")

    # Build V2 definition
    artifacts = [
        streamlit.main_file,
        environment_file,
        pages_dir,
    ]
    artifacts = [a for a in artifacts if a is not None]

    if streamlit.additional_source_files:
        artifacts.extend(streamlit.additional_source_files)

    identifier = {"name": streamlit.name}
    if streamlit.schema_name:
        identifier["schema"] = streamlit.schema_name
    if streamlit.database:
        identifier["database"] = streamlit.database

    streamlit_name = (
        "streamlit_entity_1"
        if is_name_a_templated_one(streamlit.name)
        else streamlit.name
    )

    data = {
        "entities": {
            streamlit_name: {
                "type": "streamlit",
                "identifier": identifier,
                "title": streamlit.title,
                "query_warehouse": streamlit.query_warehouse,
                "main_file": str(streamlit.main_file),
                "pages_dir": str(streamlit.pages_dir),
                "stage": streamlit.stage,
                "artifacts": artifacts,
            }
        }
    }
    return data


def convert_native_app_to_v2_data(
    project_root, native_app: NativeApp
) -> Dict[str, Any]:
    def _make_meta(obj: Application | Package):
        meta = {}
        if obj.role:
            meta["role"] = obj.role
        if obj.warehouse:
            meta["warehouse"] = obj.warehouse
        if obj.post_deploy:
            meta["post_deploy"] = obj.post_deploy
        return meta

    def _find_manifest():
        # We don't know which file in the project directory is the actual manifest,
        # and we can't iterate through the artifacts property since the src can contain
        # glob patterns. The simplest solution is to bundle the app and find the
        # manifest file from the resultant BundleMap, since the bundle process ensures
        # that only a single source path can map to the corresponding destination path
        try:
            bundle_map = build_bundle(
                project_root, Path(native_app.deploy_root), native_app.artifacts
            )
        except Exception as e:
            # The manifest field is required, so we can't gracefully handle bundle failures
            raise ClickException(
                f"{e}\nCould not bundle Native App artifacts, unable to perform migration"
            ) from e

        manifest_path = bundle_map.to_project_path(Path("manifest.yml"))
        if not manifest_path:
            # The manifest field is required, so we can't gracefully handle it being missing
            raise ClickException(
                "manifest.yml file not found in any Native App artifact sources, "
                "unable to perform migration"
            )

        # Use a POSIX path to be consistent with other migrated fields
        # which use POSIX paths as default values
        return manifest_path.as_posix()

    package_entity_name = "pkg"
    package = {
        "type": "application package",
        "identifier": (
            native_app.package.name
            if native_app.package and native_app.package.name
            else f"{native_app.name}_pkg"
        ),
        "manifest": _find_manifest(),
        "artifacts": native_app.artifacts,
        "bundle_root": native_app.bundle_root,
        "generated_root": native_app.generated_root,
        "deploy_root": native_app.deploy_root,
        "stage": native_app.source_stage,
        "scratch_stage": native_app.scratch_stage,
    }
    if native_app.package:
        package["distribution"] = native_app.package.distribution
        if package_meta := _make_meta(native_app.package):
            package["meta"] = package_meta
        # todo migrate package scripts (requires migrating template tags)

    app_entity_name = "app"
    app = {
        "type": "application",
        "identifier": (
            native_app.application.name
            if native_app.application and native_app.application.name
            else native_app.name
        ),
        "from": {"target": package_entity_name},
    }
    if native_app.application:
        if app_meta := _make_meta(native_app.application):
            app["meta"] = app_meta

    return {
        "entities": {
            package_entity_name: package,
            app_entity_name: app,
        }
    }


def convert_envs_to_v2(pd: ProjectDefinition):
    if hasattr(pd, "env") and pd.env:
        data = {k: v for k, v in pd.env.items()}
        return data
    return None


def _check_if_project_definition_meets_requirements(
    pd: ProjectDefinition, accept_templates: bool
):
    if pd.meets_version_requirement("2"):
        raise ClickException("Project definition is already at version 2.")

    if PROJECT_TEMPLATE_VARIABLE_OPENING in str(pd):
        if not accept_templates:
            raise ClickException(
                "Project definition contains templates. They may not be migrated correctly, and require manual migration."
                "You can try again with --accept-templates  option, to attempt automatic migration."
            )
        log.warning(
            "Your V1 definition contains templates. We cannot guarantee the correctness of the migration."
        )
    if pd.native_app and pd.native_app.package and pd.native_app.package.scripts:
        raise ClickException(
            "Your project file contains a native app definition that uses package scripts. "
            "Package scripts are not supported in definition version 2 and require manual conversion "
            "to post-deploy scripts."
        )


def _process_streamlit_files(
    file_name: Optional[str], file_type: Literal["pages", "environment"]
):
    default = DEFAULT_PAGES_DIR if file_type == "pages" else DEFAULT_ENV_FILE

    if file_name and not Path(file_name).exists():
        raise ClickException(f"Provided file {file_name} does not exist")
    elif file_name is None and Path(default).exists():
        file_name = default
    return file_name


def get_list_of_all_entities(
    snowpark_entities: Dict[str, Any],
    streamlit_entities: Dict[str, Any],
    native_app_entities: Dict[str, Any],
):
    # Check all combinations of entity types for overlapping names
    # (No need to use itertools here, PDFv1 only supports these three types)
    for types, first, second in [
        ("streamlit and snowpark", streamlit_entities, snowpark_entities),
        ("streamlit and native app", streamlit_entities, native_app_entities),
        ("native app and snowpark", native_app_entities, snowpark_entities),
    ]:
        if first.keys() & second.keys():
            raise ClickException(
                f"In your project, {types} entities share the same name. Please rename them and try again."
            )
    return snowpark_entities | streamlit_entities | native_app_entities