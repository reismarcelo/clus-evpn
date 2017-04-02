""" CLUS-EVPN - NSO EVPN project for Cisco Live US 2017
"""
from __future__ import absolute_import, division, print_function
from builtins import (ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round,
                      super, zip)
from builtins import str as text
import ncs.template
import resource_manager.id_allocator as id_allocator
import resource_manager.ipaddress_allocator as net_allocator
import re
import collections
_tm = __import__(ncs.tm.TM)


# ---------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------

def apply_template(template_name, context, var_dict=None):
    template = ncs.template.Template(context)
    t_vars = ncs.template.Variables()

    if var_dict is not None:
        for name, value in var_dict.items():
            t_vars.add(name, value)

    template.apply(template_name, t_vars)


def get_device_asn(root, device_name):
    bgp = next(iter(root.devices.device[device_name].config.nx__router.bgp), None)
    if bgp is None:
        raise NcsServiceConfigError('BGP not configured on node "{}"'.format(device_name))

    return bgp.id


def value_or_empty(value):
    """
    Return the provided value if it is not None, otherwise return an empty string
    This is needed in order to avoid the corresponding template nodes from being rendered.

    :param value:
    :return: value or an empty string
    """
    return value or ''


class Allocation(object):
    type = collections.namedtuple("_", "id address")(1, 2)

    request_function = {
        type.id: id_allocator.id_request,
        type.address: net_allocator.net_request,
    }
    read_function = {
        type.id: id_allocator.id_read,
        type.address: net_allocator.net_read,
    }

    def __init__(self, allocation_type, allocation_pool, allocation_id, **extra_args):
        self.type = allocation_type
        self.pool = allocation_pool
        self.id = allocation_id
        self.extra_args = extra_args

    def request(self, service, service_xpath, user):
        params = [service, service_xpath, user, self.pool, self.id]
        if self.type is Allocation.type.id:
            params.extend([False, -1])
        elif self.type is Allocation.type.address:
            params.extend([self.extra_args['length']])

        Allocation.request_function[self.type](*params)

    def read(self, user, root):
        return Allocation.read_function[self.type](user, root, self.pool, self.id)

    def __str__(self):
        return self.id


class BatchAllocator(object):
    def __init__(self, user, root, service):
        self._user = user
        self._root = root
        self._service = service
        self._service_xpath = get_xpath(service)
        self._request_queue = []
        self._allocations = []

    def __len__(self):
        return len(self._request_queue)

    def __str__(self):
        return ', '.join(map(str, self._request_queue))

    def enqueue(self, request_type, request_pool, request_id_params, **extra_args):
        self._request_queue.append(
            Allocation(request_type, request_pool, '_'.join(request_id_params), **extra_args)
        )

    def request(self):
        # Perform all allocation requests
        for allocation_request in self._request_queue:
            allocation_request.request(self._service, self._service_xpath, self._user)

        # Read allocated values only after all requests have been made to avoid multiple reactive service callbacks
        for allocation_request in self._request_queue:
            allocated_value = allocation_request.read(self._user, self._root)

            if allocated_value is None:
                return 'Allocation {} is not ready.'.format(allocation_request.id)

            self._allocations.append(allocated_value)

        return None

    @property
    def allocations(self):
        if len(self._request_queue) != len(self._allocations):
            raise AllocationsNotReady('Read too soon. Allocations are not ready!')

        return self._allocations


def get_key_yang(node):
    """
    Return the yang names corresponding to the node's key(s)

    :param node: a Maagic List
    :return: list of key yang names or None if node doesn't have any key element
    """

    # keys() returns None if node doesn't have any key (e.g. not a List)
    key_hashes = node._cs_node.info().keys()

    return key_hashes and [_tm.hash2str(key_hash) for key_hash in key_hashes]


def get_xpath(service_node):
    """
    Get an xpath that resolves to the provided service node element

    Example:
        service_node: /ncs:services/ciscoas:l3-default{CUSTOMER1-L3-DEFAULT-1 Vancouver}
        return: /ncs:services/ciscoas:l3-default[service-id='CUSTOMER1-L3-DEFAULT-1'][dc-name='Vancouver']

    Please note that this function only supports service_node with a single list in its keypath. Keypaths with
    concatenated lists are not supported and will produce unexpected results.

    :param service_node: a service node object
    :return: xpath string
    """

    def replace_match(match):
        key_values = match.group(1).split()
        return ''.join(map(lambda name_value: "[{}='{}']".format(name_value[0], name_value[1]),
                           zip(service_key_names, key_values)))

    service_key_names = get_key_yang(service_node)

    return re.sub(r'{([^}]+)}', replace_match, service_node._path)


# ---------------------------------------------
# Exceptions
# ---------------------------------------------
class NcsServiceConfigError(Exception):
    """ Exception indicating an inconsistent service configuration """
    pass


class AllocationsNotReady(Exception):
    """ Exception indicating that requested allocations are not yet ready """
    pass
