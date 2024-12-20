# Copyright (c) 2024 Snowflake Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

import yaml
from snowflake.cli._plugins.object.common import Tag
from snowflake.cli._plugins.spcs.common import (
    NoPropertiesProvidedError,
    filter_log_timestamp,
    handle_object_already_exists,
    new_logs_only,
    strip_empty_lines,
)
from snowflake.cli.api.constants import DEFAULT_SIZE_LIMIT_MB, ObjectType
from snowflake.cli.api.secure_path import SecurePath
from snowflake.cli.api.sql_execution import SqlExecutionMixin
from snowflake.connector.cursor import SnowflakeCursor
from snowflake.connector.errors import ProgrammingError


class ServiceManager(SqlExecutionMixin):
    def create(
        self,
        service_name: str,
        compute_pool: str,
        spec_path: Path,
        min_instances: int,
        max_instances: int,
        auto_resume: bool,
        external_access_integrations: Optional[List[str]],
        query_warehouse: Optional[str],
        tags: Optional[List[Tag]],
        comment: Optional[str],
        if_not_exists: bool,
    ) -> SnowflakeCursor:
        spec = self._read_yaml(spec_path)
        create_statement = "CREATE SERVICE"
        if if_not_exists:
            create_statement = f"{create_statement} IF NOT EXISTS"
        query = f"""\
            {create_statement} {service_name}
            IN COMPUTE POOL {compute_pool}
            FROM SPECIFICATION $$
            {spec}
            $$
            MIN_INSTANCES = {min_instances}
            MAX_INSTANCES = {max_instances}
            AUTO_RESUME = {auto_resume}
            """.splitlines()

        if external_access_integrations:
            external_access_integration_list = ",".join(
                f"{e}" for e in external_access_integrations
            )
            query.append(
                f"EXTERNAL_ACCESS_INTEGRATIONS = ({external_access_integration_list})"
            )

        if query_warehouse:
            query.append(f"QUERY_WAREHOUSE = {query_warehouse}")

        if comment:
            query.append(f"COMMENT = {comment}")

        if tags:
            tag_list = ",".join(f"{t.name}={t.value_string_literal()}" for t in tags)
            query.append(f"WITH TAG ({tag_list})")

        try:
            return self.execute_query(strip_empty_lines(query))
        except ProgrammingError as e:
            handle_object_already_exists(e, ObjectType.SERVICE, service_name)

    def execute_job(
        self,
        job_service_name: str,
        compute_pool: str,
        spec_path: Path,
        external_access_integrations: Optional[List[str]],
        query_warehouse: Optional[str],
        comment: Optional[str],
    ) -> SnowflakeCursor:
        spec = self._read_yaml(spec_path)
        query = f"""\
                EXECUTE JOB SERVICE
                IN COMPUTE POOL {compute_pool}
                FROM SPECIFICATION $$
                {spec}
                $$
                NAME = {job_service_name}
                """.splitlines()

        if external_access_integrations:
            external_access_integration_list = ",".join(
                f"{e}" for e in external_access_integrations
            )
            query.append(
                f"EXTERNAL_ACCESS_INTEGRATIONS = ({external_access_integration_list})"
            )

        if query_warehouse:
            query.append(f"QUERY_WAREHOUSE = {query_warehouse}")

        if comment:
            query.append(f"COMMENT = {comment}")

        try:
            return self.execute_query(strip_empty_lines(query))
        except ProgrammingError as e:
            handle_object_already_exists(e, ObjectType.SERVICE, job_service_name)

    def _read_yaml(self, path: Path) -> str:
        # TODO(aivanou): Add validation towards schema
        with SecurePath(path).open("r", read_file_limit_mb=DEFAULT_SIZE_LIMIT_MB) as fh:
            data = yaml.safe_load(fh)
        return json.dumps(data)

    def status(self, service_name: str) -> SnowflakeCursor:
        return self.execute_query(f"CALL SYSTEM$GET_SERVICE_STATUS('{service_name}')")

    def logs(
        self,
        service_name: str,
        instance_id: str,
        container_name: str,
        num_lines: int,
        previous_logs: bool = False,
        since_timestamp: str = "",
        include_timestamps: bool = False,
    ):
        cursor = self.execute_query(
            f"call SYSTEM$GET_SERVICE_LOGS('{service_name}', '{instance_id}', '{container_name}', "
            f"{num_lines}, {previous_logs}, '{since_timestamp}', {include_timestamps});"
        )

        for log in cursor.fetchall():
            yield log[0] if isinstance(log, tuple) else log

    def stream_logs(
        self,
        service_name: str,
        instance_id: str,
        container_name: str,
        num_lines: int,
        since_timestamp: str,
        include_timestamps: bool,
        interval_seconds: int,
    ):
        try:
            prev_timestamp = since_timestamp
            prev_log_records: List[str] = []

            while True:
                raw_log_blocks = [
                    log
                    for log in self.logs(
                        service_name=service_name,
                        instance_id=instance_id,
                        container_name=container_name,
                        num_lines=num_lines,
                        since_timestamp=prev_timestamp,
                        include_timestamps=True,
                    )
                ]

                new_log_records = []
                for block in raw_log_blocks:
                    new_log_records.extend(block.split("\n"))

                new_log_records = [line for line in new_log_records if line.strip()]

                if new_log_records:
                    dedup_log_records = new_logs_only(prev_log_records, new_log_records)
                    for log in dedup_log_records:
                        yield filter_log_timestamp(log, include_timestamps)

                    prev_timestamp = dedup_log_records[-1].split(" ", 1)[0]
                    prev_log_records = dedup_log_records

                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            return

    def upgrade_spec(self, service_name: str, spec_path: Path):
        spec = self._read_yaml(spec_path)
        query = f"alter service {service_name} from specification $$ {spec} $$"
        return self.execute_query(query)

    def list_endpoints(self, service_name: str) -> SnowflakeCursor:
        return self.execute_query(f"show endpoints in service {service_name}")

    def list_instances(self, service_name: str) -> SnowflakeCursor:
        return self.execute_query(f"show service instances in service {service_name}")

    def list_containers(self, service_name: str) -> SnowflakeCursor:
        return self.execute_query(f"show service containers in service {service_name}")

    def list_roles(self, service_name: str) -> SnowflakeCursor:
        return self.execute_query(f"show roles in service {service_name}")

    def suspend(self, service_name: str):
        return self.execute_query(f"alter service {service_name} suspend")

    def resume(self, service_name: str):
        return self.execute_query(f"alter service {service_name} resume")

    def set_property(
        self,
        service_name: str,
        min_instances: Optional[int],
        max_instances: Optional[int],
        query_warehouse: Optional[str],
        auto_resume: Optional[bool],
        external_access_integrations: Optional[List[str]],
        comment: Optional[str],
    ):
        property_pairs = [
            ("min_instances", min_instances),
            ("max_instances", max_instances),
            ("query_warehouse", query_warehouse),
            ("auto_resume", auto_resume),
            ("external_access_integrations", external_access_integrations),
            ("comment", comment),
        ]

        # Check if all provided properties are set to None (no properties are being set)
        if all([value is None for property_name, value in property_pairs]):
            raise NoPropertiesProvidedError(
                f"No properties specified for service '{service_name}'. Please provide at least one property to set."
            )
        query: List[str] = [f"alter service {service_name} set "]

        if min_instances is not None:
            query.append(f" min_instances = {min_instances}")

        if max_instances is not None:
            query.append(f" max_instances = {max_instances}")

        if query_warehouse is not None:
            query.append(f" query_warehouse = {query_warehouse}")

        if auto_resume is not None:
            query.append(f" auto_resume = {auto_resume}")

        if external_access_integrations is not None:
            external_access_integration_list = ",".join(
                f"{e}" for e in external_access_integrations
            )
            query.append(
                f"external_access_integrations = ({external_access_integration_list})"
            )

        if comment is not None:
            query.append(f" comment = {comment}")

        return self.execute_query(strip_empty_lines(query))

    def unset_property(
        self,
        service_name: str,
        min_instances: bool,
        max_instances: bool,
        query_warehouse: bool,
        auto_resume: bool,
        comment: bool,
    ):
        property_pairs = [
            ("min_instances", min_instances),
            ("max_instances", max_instances),
            ("query_warehouse", query_warehouse),
            ("auto_resume", auto_resume),
            ("comment", comment),
        ]

        # Check if all properties provided are False (no properties are being unset)
        if not any([value for property_name, value in property_pairs]):
            raise NoPropertiesProvidedError(
                f"No properties specified for service '{service_name}'. Please provide at least one property to reset to its default value."
            )
        unset_list = [property_name for property_name, value in property_pairs if value]
        query = f"alter service {service_name} unset {','.join(unset_list)}"
        return self.execute_query(query)
