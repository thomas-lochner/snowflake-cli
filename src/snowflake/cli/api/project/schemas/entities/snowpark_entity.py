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

from typing import Dict, List, Literal, Optional, Union

from pydantic import Field, field_validator
from snowflake.cli.api.project.schemas.entities.common import EntityModelBase
from snowflake.cli.api.project.schemas.snowpark.argument import Argument
from snowflake.cli.api.project.schemas.updatable_model import DiscriminatorField


class SnowparkEntityModel(EntityModelBase):
    handler: str = Field(
        title="Function’s or procedure’s implementation of the object inside source module",
        examples=["functions.hello_function"],
    )
    returns: str = Field(
        title="Type of the result"
    )  # TODO: again, consider Literal/Enum
    signature: Union[str, List[Argument]] = Field(
        title="The signature parameter describes consecutive arguments passed to the object"
    )
    runtime: Optional[Union[str, float]] = Field(
        title="Python version to use when executing ", default=None
    )
    external_access_integrations: Optional[List[str]] = Field(
        title="Names of external access integrations needed for this procedure’s handler code to access external networks",
        default=[],
    )
    secrets: Optional[Dict[str, str]] = Field(
        title="Assigns the names of secrets to variables so that you can use the variables to reference the secrets",
        default={},
    )
    imports: Optional[List[str]] = Field(
        title="Stage and path to previously uploaded files you want to import",
        default=[],
    )
    stage: str = Field(title="Stage in which artifacts will be stored")
    artifacts: str = Field(title="Folder where your code should be located")

    @field_validator("runtime")
    @classmethod
    def convert_runtime(cls, runtime_input: Union[str, float]) -> str:
        if isinstance(runtime_input, float):
            return str(runtime_input)
        return runtime_input


class ProcedureEntityModel(SnowparkEntityModel):
    type: Literal["procedure"] = DiscriminatorField()  # noqa: A003
    execute_as_caller: Optional[bool] = Field(
        title="Determine whether the procedure is executed with the privileges of "
        "the owner (you) or with the privileges of the caller",
        default=False,
    )


class FunctionEntityModel(SnowparkEntityModel):
    type: Literal["function"] = DiscriminatorField()  # noqa: A003