# Copyright 2013 Cisco Systems, Inc.
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

import collections
import contextlib
import hashlib

from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils

from neutron_lib._i18n import _
from neutron_lib import constants
from neutron_lib import exceptions


LOG = logging.getLogger(__name__)
INTERFACE_HASH_LEN = 6


def _is_valid_range(val, min, max):
    try:
        # NOTE: use str value to not permit booleans
        val = int(str(val))
        return min <= val <= max
    except (ValueError, TypeError):
        return False


def is_valid_vlan_tag(vlan):
    """Validate a VLAN tag.

    :param vlan: The VLAN tag to validate.
    :returns: True if vlan is a number that is a valid VLAN tag.
    """
    return _is_valid_range(
        vlan, constants.MIN_VLAN_TAG, constants.MAX_VLAN_TAG)


def is_valid_gre_id(gre_id):
    """Validate a GRE ID.

    :param gre_id: The GRE ID to validate.
    :returns: True if gre_id is a number that's a valid GRE ID.
    """
    return _is_valid_range(
        gre_id, constants.MIN_GRE_ID, constants.MAX_GRE_ID)


def is_valid_vxlan_vni(vni):
    """Validate a VXLAN VNI.

    :param vni: The VNI to validate.
    :returns: True if vni is a number that's a valid VXLAN VNI.
    """
    return _is_valid_range(
        vni, constants.MIN_VXLAN_VNI, constants.MAX_VXLAN_VNI)


def is_valid_geneve_vni(vni):
    """Validate a Geneve VNI

    :param vni: The VNI to validate.
    :returns: True if vni is a number that's a valid Geneve VNI.
    """
    return _is_valid_range(
        vni, constants.MIN_GENEVE_VNI, constants.MAX_GENEVE_VNI)


_TUNNEL_MAPPINGS = {
    constants.TYPE_GRE: is_valid_gre_id,
    constants.TYPE_VXLAN: is_valid_vxlan_vni,
    constants.TYPE_GENEVE: is_valid_geneve_vni
}


def verify_tunnel_range(tunnel_range, tunnel_type):
    """Verify a given tunnel range is valid given it's tunnel type.

    Existing validation is done for GRE, VXLAN and GENEVE types as per
    _TUNNEL_MAPPINGS.

    :param tunnel_range: An iterable who's 0 index is the min tunnel range
        and who's 1 index is the max tunnel range.
    :param tunnel_type: The tunnel type of the range.
    :returns: None if the tunnel_range is valid.
    :raises: NetworkTunnelRangeError if tunnel_range is invalid.
    """
    if tunnel_type in _TUNNEL_MAPPINGS:
        for ident in tunnel_range:
            if not _TUNNEL_MAPPINGS[tunnel_type](ident):
                raise exceptions.NetworkTunnelRangeError(
                    tunnel_range=tunnel_range,
                    error=_("%(id)s is not a valid %(type)s identifier") %
                    {'id': ident, 'type': tunnel_type})
    if tunnel_range[1] < tunnel_range[0]:
        raise exceptions.NetworkTunnelRangeError(
            tunnel_range=tunnel_range,
            error=_("End of tunnel range is less "
                    "than start of tunnel range"))


def _raise_invalid_tag(vlan_str, vlan_range):
    """Raise an exception for invalid tag."""
    raise exceptions.NetworkVlanRangeError(
        vlan_range=vlan_range,
        error=_("%s is not a valid VLAN tag") % vlan_str)


def verify_vlan_range(vlan_range):
    """Verify a VLAN range is valid.

    :param vlan_range: An iterable who's 0 index is the min tunnel range
        and who's 1 index is the max tunnel range.
    :returns: None if the vlan_range is valid.
    :raises: NetworkVlanRangeError if vlan_range is not valid.
    """
    for vlan_tag in vlan_range:
        if not is_valid_vlan_tag(vlan_tag):
            _raise_invalid_tag(str(vlan_tag), vlan_range)
    if vlan_range[1] < vlan_range[0]:
        raise exceptions.NetworkVlanRangeError(
            vlan_range=vlan_range,
            error=_("End of VLAN range is less than start of VLAN range"))


def parse_network_vlan_range(network_vlan_range):
    """Parse a well formed network VLAN range string.

    The network VLAN range string has the format:
        network[:vlan_begin:vlan_end]

    :param network_vlan_range: The network VLAN range string to parse.
    :returns: A tuple who's 1st element is the network name and 2nd
        element is the VLAN range parsed from network_vlan_range.
    :raises: NetworkVlanRangeError if network_vlan_range is malformed.
        PhysicalNetworkNameError if network_vlan_range is missing a network
        name.
    """
    entry = network_vlan_range.strip()
    if ':' in entry:
        if entry.count(':') != 2:
            raise exceptions.NetworkVlanRangeError(
                vlan_range=entry,
                error=_("Need exactly two values for VLAN range"))
        network, vlan_min, vlan_max = entry.split(':')
        if not network:
            raise exceptions.PhysicalNetworkNameError()

        try:
            vlan_min = int(vlan_min)
        except ValueError:
            _raise_invalid_tag(vlan_min, entry)

        try:
            vlan_max = int(vlan_max)
        except ValueError:
            _raise_invalid_tag(vlan_max, entry)

        vlan_range = (vlan_min, vlan_max)
        verify_vlan_range(vlan_range)
        return network, vlan_range
    else:
        return entry, None


def parse_network_vlan_ranges(network_vlan_ranges_cfg_entries):
    """Parse a list of well formed network VLAN range string.

    Behaves like parse_network_vlan_range, but parses a list of
    network VLAN strings into an ordered dict.

    :param network_vlan_ranges_cfg_entries: The list of network VLAN
        strings to parse.
    :returns: An OrderedDict who's keys are network names and values are
        the list of VLAN ranges parsed.
    :raises: See parse_network_vlan_range.
    """
    networks = collections.OrderedDict()
    for entry in network_vlan_ranges_cfg_entries:
        network, vlan_range = parse_network_vlan_range(entry)
        if vlan_range:
            networks.setdefault(network, []).append(vlan_range)
        else:
            networks.setdefault(network, [])
    return networks


def in_pending_status(status):
    """Return True if status is a form of pending"""
    return status in (constants.PENDING_CREATE,
                      constants.PENDING_UPDATE,
                      constants.PENDING_DELETE)


@contextlib.contextmanager
def delete_port_on_error(core_plugin, context, port_id):
    """A decorator that deletes a port upon exception.

    This decorator can be used to wrap a block of code that
    should delete a port if an exception is raised during the block's
    execution.

    :param core_plugin: The core plugin implementing the delete_port method to
        call.
    :param context: The context.
    :param port_id: The port's ID.
    :returns: None
    """
    try:
        yield
    except Exception:
        with excutils.save_and_reraise_exception():
            try:
                core_plugin.delete_port(context, port_id,
                                        l3_port_check=False)
            except exceptions.PortNotFound:
                LOG.debug("Port %s not found", port_id)
            except Exception:
                LOG.exception("Failed to delete port: %s", port_id)


@contextlib.contextmanager
def update_port_on_error(core_plugin, context, port_id, revert_value):
    """A decorator that updates a port upon exception.

    This decorator can be used to wrap a block of code that
    should update a port if an exception is raised during the block's
    execution.

    :param core_plugin: The core plugin implementing the update_port method to
        call.
    :param context: The context.
    :param port_id: The port's ID.
    :param revert_value: The value to revert on the port object.
    :returns: None
    """
    try:
        yield
    except Exception:
        with excutils.save_and_reraise_exception():
            try:
                core_plugin.update_port(context, port_id,
                                        {'port': revert_value})
            except Exception:
                LOG.exception("Failed to update port: %s", port_id)


def get_interface_name(name, prefix='', max_len=constants.DEVICE_NAME_MAX_LEN):
    """Construct an interface name based on the prefix and name.

    The interface name can not exceed the maximum length passed in. Longer
    names are hashed to help ensure uniqueness.
    """
    requested_name = prefix + name

    if len(requested_name) <= max_len:
        return requested_name

    # We can't just truncate because interfaces may be distinguished
    # by an ident at the end. A hash over the name should be unique.
    # Leave part of the interface name on for easier identification
    if (len(prefix) + INTERFACE_HASH_LEN) > max_len:
        raise ValueError(_("Too long prefix provided. New name would exceed "
                           "given length for an interface name."))

    namelen = max_len - len(prefix) - INTERFACE_HASH_LEN
    hashed_name = hashlib.sha1(encodeutils.to_utf8(name))
    new_name = ('%(prefix)s%(truncated)s%(hash)s' %
                {'prefix': prefix, 'truncated': name[0:namelen],
                 'hash': hashed_name.hexdigest()[0:INTERFACE_HASH_LEN]})
    LOG.info("The requested interface name %(requested_name)s exceeds the "
             "%(limit)d character limitation. It was shortened to "
             "%(new_name)s to fit.",
             {'requested_name': requested_name,
              'limit': max_len, 'new_name': new_name})
    return new_name
