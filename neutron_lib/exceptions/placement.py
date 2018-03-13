# All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from neutron_lib._i18n import _
from neutron_lib import exceptions


class PlacementEndpointNotFound(exceptions.NotFound):
    message = _("Placement API endpoint not found.")


class PlacementResourceProviderNotFound(exceptions.NotFound):
    message = _("Placement resource provider not found %(resource_provider)s.")


class PlacementInventoryNotFound(exceptions.NotFound):
    message = _("Placement inventory not found for resource provider "
                "%(resource_provider)s, resource class %(resource_class)s.")


class PlacementInventoryUpdateConflict(exceptions.Conflict):
    message = _("Placement inventory update conflict for resource provider "
                "%(resource_provider)s, resource class %(resource_class)s.")


class PlacementAggregateNotFound(exceptions.NotFound):
    message = _("Aggregate not found for resource provider "
                "%(resource_provider)s.")


class PlacementAPIVersionIncorrect(exceptions.NotFound):
    message = _("Placement API version %(current_version)s, do not meet the"
                "needed version %(needed_version)s.")
