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

from webob import exc

from neutron_lib._i18n import _
from neutron_lib.api.definitions import network
from neutron_lib.api.definitions import port
from neutron_lib.api.definitions import subnet
from neutron_lib.api.definitions import subnetpool
from neutron_lib.api import validators
from neutron_lib import constants
from neutron_lib import exceptions


def _validate_privileges(context, res_dict):
    if ('project_id' in res_dict and
            res_dict['project_id'] != context.project_id and
            not context.is_admin):
        msg = _("Specifying 'project_id' or 'tenant_id' other than the "
                "authenticated project in request requires admin privileges")
        raise exc.HTTPBadRequest(msg)


#为了升级方便提供的project_id,tenant_id的转换
def populate_project_info(attributes):
    """Ensure that both project_id and tenant_id attributes are present.

    If either project_id or tenant_id is present in attributes then ensure
    that both are present.

    If neither are present then attributes is not updated.

    :param attributes: A dictionary of resource/API attributes
        or API request/response dict.
    :returns: attributes (updated with project_id if applicable).
    :raises: HTTPBadRequest if the attributes project_id and tenant_id
        don't match.
    """
    if 'tenant_id' in attributes and 'project_id' not in attributes:
        #原属性中有tenant_id,没有project_id,则更新为project_id
        attributes['project_id'] = attributes['tenant_id']
    elif 'project_id' in attributes and 'tenant_id' not in attributes:
        #属性中已有project_id,但无tenant_id，则增加tenant_id
        # Backward compatibility for code still using tenant_id
        attributes['tenant_id'] = attributes['project_id']

    #如果两者不相等，报错
    if attributes.get('project_id') != attributes.get('tenant_id'):
        msg = _("'project_id' and 'tenant_id' do not match")
        raise exc.HTTPBadRequest(msg)

    return attributes


class AttributeInfo(object):
    """Provides operations on a resource's attribute map.

    AttributeInfo wraps an API resource's attribute dict and provides methods
    for filling defaults, validating, converting, etc. based on the
    underlying attributes.
    """

    def __init__(self, resource_attrs):
        """Create a new instance that wraps the given resource attributes.

        :param resource_attrs: The resource's attributes that can be any
            of the following types: an instance of AttributeInfo, an API
            definition that contains a RESOURCE_ATTRIBUTE_MAP attribute or
            a dict of attributes for the resource.
        """
        if isinstance(resource_attrs, AttributeInfo):
            resource_attrs = resource_attrs.attributes
        elif getattr(resource_attrs,
                     'RESOURCE_ATTRIBUTE_MAP', None) is not None:
            # handle neutron_lib API definitions
            resource_attrs = resource_attrs.RESOURCE_ATTRIBUTE_MAP

        self.attributes = resource_attrs

    def fill_post_defaults(
            self, res_dict,
            exc_cls=lambda m: exceptions.InvalidInput(error_message=m),
            check_allow_post=True):
        """Fill in default values for attributes in a POST request.

        When a POST request is made, the attributes with default values do not
        need to be specified by the user. This function fills in the values of
        any unspecified attributes if they have a default value.

        If an attribute is not specified and it does not have a default value,
        an exception is raised.

        If an attribute is specified and it is not allowed in POST requests, an
        exception is raised. The caller can override this behavior by setting
        check_allow_post=False (used by some internal admin operations).

        :param res_dict: The resource attributes from the request.
        :param exc_cls: Exception to be raised on error that must take
            a single error message as it's only constructor arg.
        :param check_allow_post: Raises an exception if a non-POST-able
            attribute is specified.
        :raises: exc_cls If check_allow_post is True and this instance of
            ResourceAttributes doesn't support POST.
        """
        for attr, attr_vals in self.attributes.items():
            if attr_vals['allow_post']:
                if 'default' not in attr_vals and attr not in res_dict:
                    msg = _("Failed to parse request. Required "
                            "attribute '%s' not specified") % attr
                    raise exc_cls(msg)
                res_dict[attr] = res_dict.get(attr,
                                              attr_vals.get('default'))
            elif check_allow_post:
                if attr in res_dict:
                    msg = _("Attribute '%s' not allowed in POST") % attr
                    raise exc_cls(msg)

    def convert_values(
            self, res_dict,
            exc_cls=lambda m: exceptions.InvalidInput(error_message=m)):
        """Convert and validate attribute values for a request.

        :param res_dict: The resource attributes from the request.
        :param exc_cls: Exception to be raised on error that must take
            a single error message as it's only constructor arg.
        :raises: exc_cls If any errors occur converting/validating the
            res_dict.
        """
        for attr, attr_vals in self.attributes.items():
            if (attr not in res_dict or
                    res_dict[attr] is constants.ATTR_NOT_SPECIFIED):
                continue
            # Convert values if necessary
            if 'convert_to' in attr_vals:
                res_dict[attr] = attr_vals['convert_to'](res_dict[attr])
            # Check that configured values are correct
            if 'validate' not in attr_vals:
                continue
            for rule in attr_vals['validate']:
                validator = validators.get_validator(rule)
                res = validator(res_dict[attr], attr_vals['validate'][rule])

                if res:
                    msg_dict = dict(attr=attr, reason=res)
                    msg = _("Invalid input for %(attr)s. "
                            "Reason: %(reason)s.") % msg_dict
                    raise exc_cls(msg)

    def populate_project_id(self, context, res_dict, is_create):
        """Populate the owner information in a request body.

        Ensure both project_id and tenant_id attributes are present.
        Validate that the requestor has the required privileges.
        For a create request, copy owner info from context to request body
        if needed and verify that owner is specified if required.

        :param context: The request context.
        :param res_dict: The resource attributes from the request.
        :param attr_info: The attribute map for the resource.
        :param is_create: Is this a create request?
        :raises: HTTPBadRequest If neither the project_id nor tenant_id
            are specified in the res_dict.

        """
        populate_project_info(res_dict)
        _validate_privileges(context, res_dict)

        if is_create and 'project_id' not in res_dict:
            if context.project_id:
                res_dict['project_id'] = context.project_id

                # For backward compatibility
                res_dict['tenant_id'] = context.project_id

            elif 'tenant_id' in self.attributes:
                msg = _("Running without keystone AuthN requires "
                        "that tenant_id is specified")
                raise exc.HTTPBadRequest(msg)

    def verify_attributes(self, attrs_to_verify):
        """Reject unknown attributes.

        Consumers should ensure the project info is populated in the
        attrs_to_verify before calling this method.

        :param attrs_to_verify: The attributes to verify against this
            resource attributes.
        :raises: HTTPBadRequest: If attrs_to_verify contains any unrecognized
            for this resource attributes instance.
        """
        extra_keys = set(attrs_to_verify.keys()) - set(self.attributes.keys())
        if extra_keys:
            msg = _("Unrecognized attribute(s) '%s'") % ', '.join(extra_keys)
            raise exc.HTTPBadRequest(msg)


def _core_resource_attributes():
    resources = {}
    for core_def in [network.RESOURCE_ATTRIBUTE_MAP,
                     port.RESOURCE_ATTRIBUTE_MAP,
                     subnet.RESOURCE_ATTRIBUTE_MAP,
                     subnetpool.RESOURCE_ATTRIBUTE_MAP]:
        resources.update(core_def)
    return resources


# populate core resources into singleton global
RESOURCES = _core_resource_attributes()
