""" CLUS-EVPN - NSO EVPN project for Cisco Live US 2017
"""
from __future__ import absolute_import, division, print_function
from builtins import (ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round,
                      super, zip)
from builtins import str as text
import ncs
from ncs.application import Service, PlanComponent
import ncs.template
import functools
from itertools import islice, chain, repeat
from ipaddress import ip_network
from vxlan.utils import (apply_template, BatchAllocator, Allocation, NcsServiceConfigError, AllocationsNotReady,
                         init_plan)


# --------------------------------------------------
# Global service configuration parameters
# --------------------------------------------------
class Config(object):
    SIRB_VLAN_POOL = 'sirb-vlan'
    LFNC_VLAN_POOL = 'lfnc-vlan'
    LFNC_IP_POOL = 'lfnc-ip'
    LFNC_IP_LENGTH = 30
    DCI_NUM_VLANS = 2
    DCI_VLAN_POOL = 'dci-vlan'
    DCI_IP_POOL = 'dci-ip'
    DCI_IP_LENGTH = 30


# --------------------------------------------------
# Service create callback decorator
# --------------------------------------------------
def evpn_service(cb_create_method):
    @functools.wraps(cb_create_method)
    def wrapper(self, tctx, root, service, proplist):
        self.log.info('Service create(service={})'.format(service))
        self_plan = init_plan(PlanComponent(service, 'self', 'ncs:self'), 'evpn:resource-allocations')
        allocator = BatchAllocator(tctx.username, root, service)

        try:
            if cb_create_method(self, tctx, root, service, proplist, self_plan, allocator):
                return
        except (NcsServiceConfigError, AllocationsNotReady) as e:
            self.log.error(e)
            self_plan.set_failed('ncs:ready')
        else:
            self_plan.set_reached('ncs:ready')

    return wrapper


# --------------------------------------------------
# L3 DIRECT SERVICE CALLBACK
# --------------------------------------------------
class L3DirectServiceCallback(Service):
    @Service.create
    @evpn_service
    def cb_create(self, tctx, root, service, proplist, self_plan, allocator):
        # Prepare allocation requests for values not provided by the user
        # SIRB VLAN
        if service.sirb_vlan is None:
            allocator.enqueue(Allocation.type.id, Config.SIRB_VLAN_POOL, ['SIRB_VLAN', service.service_id])
        # LFNC VLAN, ip address
        if service.lfnc_vlan is None:
            allocator.enqueue(Allocation.type.id, Config.LFNC_VLAN_POOL, ['LFNC_VLAN', service.service_id])
        if service.lfnc_ip_address is None:
            allocator.enqueue(Allocation.type.address, Config.LFNC_IP_POOL, ['LFNC_IP', service.service_id],
                              length=Config.LFNC_IP_LENGTH)
        # DCI VLAN, subnet
        for count, dci_vlan in enumerate(islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS)):
            if dci_vlan is None:
                allocator.enqueue(Allocation.type.id, Config.DCI_VLAN_POOL,
                                  ['DCI_VLAN', service.service_id, str(count)])
            if (dci_vlan is None) or (dci_vlan.subnet is None):
                allocator.enqueue(Allocation.type.address, Config.DCI_IP_POOL,
                                  ['DCI_IP', service.service_id, str(count)], length=Config.DCI_IP_LENGTH)

        if len(allocator) > 0:
            self.log.info('Allocating: {}'.format(allocator))

        not_ready_msg = allocator.request()
        if not_ready_msg is not None:
            self.log.info(not_ready_msg)
            return True

        # Write operational data container with final values for VLANs and IPs
        # These are either the user-configured values or values assigned by BatchAllocator
        allocations_iter = iter(allocator.allocations)
        # SIRB VLAN
        service.auto_values.sirb_vlan = service.sirb_vlan or next(allocations_iter)
        # LFNC VLAN, ip address
        service.auto_values.lfnc_vlan = service.lfnc_vlan or next(allocations_iter)
        service.auto_values.lfnc_ip_address = service.lfnc_ip_address or subnet_first_host(next(allocations_iter))
        # DCI VLAN, subnet
        for dci_vlan in islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS):
            dci_vlan_id = dci_vlan.id if dci_vlan is not None else next(allocations_iter)
            if dci_vlan_id in service.auto_values.dci_vlan:
                raise NcsServiceConfigError(
                    'Configured DCI VLAN ID {} is equal to an auto-assigned VLAN ID'.format(dci_vlan_id))
            dci_vlan_node = service.auto_values.dci_vlan.create(dci_vlan_id)
            dci_vlan_node.subnet = (dci_vlan.subnet if dci_vlan is not None else None) or next(allocations_iter)

        self_plan.set_reached('evpn:resource-allocations')

        self.log.info('Rendering l3-direct template')
        service_vars = {
            'SITE-LEAF-ASN': root.plant_information.plant[service.dc_name].as_number.leaf_nodes,
        }
        apply_template('l3_direct', service, service_vars)

        self.log.info('Rendering l3 dci template')
        apply_l3_direct_default_dci_template(root, service)


# --------------------------------------------------
# L3 DEFAULT SERVICE CALLBACK
# --------------------------------------------------
class L3DefaultServiceCallback(Service):
    @Service.create
    @evpn_service
    def cb_create(self, tctx, root, service, proplist, self_plan, allocator):
        # Prepare allocation requests for values not provided by the user
        # SIRB VLAN
        if service.sirb_vlan is None:
            allocator.enqueue(Allocation.type.id, Config.SIRB_VLAN_POOL, ['SIRB_VLAN', service.service_id])
        # LFNC VLAN, ip address
        for count, leaf_node in enumerate(service.ports.leaf_node):
            if leaf_node.lfnc_vlan is None:
                allocator.enqueue(Allocation.type.id, Config.LFNC_VLAN_POOL,
                                  ['LFNC_VLAN', service.service_id, str(count)])
            if leaf_node.lfnc_ip_address is None:
                allocator.enqueue(Allocation.type.address, Config.LFNC_IP_POOL,
                                  ['LFNC_IP', service.service_id, str(count)], length=Config.LFNC_IP_LENGTH)
        # DCI VLAN, subnet
        for count, dci_vlan in enumerate(islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS)):
            if dci_vlan is None:
                allocator.enqueue(Allocation.type.id, Config.DCI_VLAN_POOL,
                                  ['DCI_VLAN', service.service_id, str(count)])
            if (dci_vlan is None) or (dci_vlan.subnet is None):
                allocator.enqueue(Allocation.type.address, Config.DCI_IP_POOL,
                                  ['DCI_IP', service.service_id, str(count)], length=Config.DCI_IP_LENGTH)

        if len(allocator) > 0:
            self.log.info('Allocating: {}'.format(allocator))

        not_ready_msg = allocator.request()
        if not_ready_msg is not None:
            self.log.info(not_ready_msg)
            return True

        # Write operational data container with final values for VLANs and IPs
        # These are either the user-configured values or values assigned by BatchAllocator
        allocations_iter = iter(allocator.allocations)
        # SIRB VLAN
        service.auto_values.sirb_vlan = service.sirb_vlan or next(allocations_iter)
        # LFNC VLAN, ip address
        for leaf_node in service.ports.leaf_node:
            node = service.auto_values.leaf_node.create(leaf_node.node_name)
            node.lfnc_vlan = leaf_node.lfnc_vlan or next(allocations_iter)
            node.lfnc_ip_address = leaf_node.lfnc_ip_address or subnet_first_host(next(allocations_iter))
        # DCI VLAN, subnet
        for dci_vlan in islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS):
            dci_vlan_id = dci_vlan.id if dci_vlan is not None else next(allocations_iter)
            if dci_vlan_id in service.auto_values.dci_vlan:
                raise NcsServiceConfigError(
                    'Configured DCI VLAN ID {} is equal to an auto-assigned VLAN ID'.format(dci_vlan_id))
            dci_vlan_node = service.auto_values.dci_vlan.create(dci_vlan_id)
            dci_vlan_node.subnet = (dci_vlan.subnet if dci_vlan is not None else None) or next(allocations_iter)

        self_plan.set_reached('evpn:resource-allocations')

        self.log.info('Rendering l3-default template')
        service_vars = {
            'SITE-LEAF-ASN': root.plant_information.plant[service.dc_name].as_number.leaf_nodes,
        }
        apply_template('l3_default', service, service_vars)

        self.log.info('Rendering l3 dci template')
        apply_l3_direct_default_dci_template(root, service)


# --------------------------------------------------
# L2 VPLS SERVICE CALLBACK
# --------------------------------------------------
class L2VplsServiceCallback(Service):
    @Service.create
    @evpn_service
    def cb_create(self, tctx, root, service, proplist, self_plan, allocator):
        # Prepare allocation requests for values not provided by the user
        # LFNC VLAN
        if service.lfnc_vlan is None:
            allocator.enqueue(Allocation.type.id, Config.LFNC_VLAN_POOL, ['LFNC_VLAN', service.service_id])
        # DCI VLAN
        for count, dci_vlan in enumerate(islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS)):
            if dci_vlan is None:
                allocator.enqueue(Allocation.type.id, Config.DCI_VLAN_POOL,
                                  ['DCI_VLAN', service.service_id, str(count)])

        if len(allocator) > 0:
            self.log.info('Allocating: {}'.format(allocator))

        not_ready_msg = allocator.request()
        if not_ready_msg is not None:
            self.log.info(not_ready_msg)
            return True

        # Write operational data container with final values for VLANs and IPs
        # These are either the user-configured values or values assigned by BatchAllocator
        allocations_iter = iter(allocator.allocations)
        # LFNC VLAN
        service.auto_values.lfnc_vlan = service.lfnc_vlan or next(allocations_iter)
        # DCI VLAN
        for dci_vlan in islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS):
            dci_vlan_id = dci_vlan.id if dci_vlan is not None else next(allocations_iter)
            if dci_vlan_id in service.auto_values.dci_vlan:
                raise NcsServiceConfigError(
                    'Configured DCI VLAN ID {} is equal to an auto-assigned VLAN ID'.format(dci_vlan_id))
            service.auto_values.dci_vlan.create(dci_vlan_id)

        self_plan.set_reached('evpn:resource-allocations')

        self.log.info('Rendering l2-vpls template')
        service_vars = {
            'SITE-LEAF-ASN': root.plant_information.plant[service.dc_name].as_number.leaf_nodes,
        }
        apply_template('l2_vpls', service, service_vars)

        self.log.info('Rendering l2 dci template')
        apply_l2_vpls_evpl_dci_template(root, service)


# --------------------------------------------------
# L2 Evpl SERVICE CALLBACK
# --------------------------------------------------
class L2EvplServiceCallback(Service):
    @Service.create
    @evpn_service
    def cb_create(self, tctx, root, service, proplist, self_plan, allocator):
        # Prepare allocation requests for values not provided by the user
        # LFNC VLAN
        if service.lfnc_vlan is None:
            allocator.enqueue(Allocation.type.id, Config.LFNC_VLAN_POOL, ['LFNC_VLAN', service.service_id])
        # DCI VLAN
        for count, dci_vlan in enumerate(islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS)):
            if dci_vlan is None:
                allocator.enqueue(Allocation.type.id, Config.DCI_VLAN_POOL,
                                  ['DCI_VLAN', service.service_id, str(count)])

        if len(allocator) > 0:
            self.log.info('Allocating: {}'.format(allocator))

        not_ready_msg = allocator.request()
        if not_ready_msg is not None:
            self.log.info(not_ready_msg)
            return True

        # Write operational data container with final values for VLANs and IPs
        # These are either the user-configured values or values assigned by BatchAllocator
        allocations_iter = iter(allocator.allocations)
        # LFNC VLAN
        service.auto_values.lfnc_vlan = service.lfnc_vlan or next(allocations_iter)
        # DCI VLAN
        for dci_vlan in islice(chain(service.dci.vlan, repeat(None)), Config.DCI_NUM_VLANS):
            dci_vlan_id = dci_vlan.id if dci_vlan is not None else next(allocations_iter)
            if dci_vlan_id in service.auto_values.dci_vlan:
                raise NcsServiceConfigError(
                    'Configured DCI VLAN ID {} is equal to an auto-assigned VLAN ID'.format(dci_vlan_id))
            service.auto_values.dci_vlan.create(dci_vlan_id)

        self_plan.set_reached('evpn:resource-allocations')

        self.log.info('Rendering l2-evpl template')
        service_vars = {
            'SITE-LEAF-ASN': root.plant_information.plant[service.dc_name].as_number.leaf_nodes,
        }
        apply_template('l2_vpls', service, service_vars)

        self.log.info('Rendering l2 dci template')
        apply_l2_vpls_evpl_dci_template(root, service)


# --------------------------------------------------
# UTILITY FUNCTIONS
# --------------------------------------------------
def apply_l3_direct_default_dci_template(root_context, service_context):
    for count, vlan in enumerate(service_context.auto_values.dci_vlan, start=1):
        dci_link_net = ip_network(text(vlan.subnet))
        dci_link_ip_list = list(dci_link_net.hosts())
        if len(dci_link_ip_list) < 2:
            raise NcsServiceConfigError('VLAN {} subnet must have at least 2 host addresses'.format(vlan.id))
        dci_vars = {
            'COUNT': count,
            'VLAN-ID': vlan.id,
            'BDR-IP': dci_link_ip_list[1],
            'BDR-LEN': dci_link_net.prefixlen,
            'DCI-IP': dci_link_ip_list[0],
            'SITE-DCI-ASN': root_context.plant_information.plant[service_context.dc_name].as_number.dci_nodes,
        }
        apply_template('l3_direct_default_dci', service_context, dci_vars)


def apply_l2_vpls_evpl_dci_template(root_context, service_context):
    for count, vlan in enumerate(service_context.auto_values.dci_vlan, start=1):
        dci_vars = {
            'COUNT': count,
            'VLAN-ID': vlan.id,
        }
        apply_template('l2_vpls_evpl_dci', service_context, dci_vars)


def subnet_first_host(subnet_str):
    """
    Return the first valid IP address in the subnet
    :param subnet_str: IP subnet as a string in <prefix>/<len> format
    :return: String representing the IP address in <prefix>/<len> format
    """
    subnet = ip_network(text(subnet_str))
    return '{}/{}'.format(next(subnet.hosts()), subnet.prefixlen)


# --------------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS
# --------------------------------------------------
class Main(ncs.application.Application):
    def setup(self):
        self.log.info('EVPN Service RUNNING')

        # Registration of service callbacks
        self.register_service('evpn-l3-direct-servicepoint', L3DirectServiceCallback)
        self.register_service('evpn-l3-default-servicepoint', L3DefaultServiceCallback)
        self.register_service('evpn-l2-vpls-servicepoint', L2VplsServiceCallback)
        self.register_service('evpn-l2-evpl-servicepoint', L2EvplServiceCallback)

    def teardown(self):
        self.log.info('EVPN Service FINISHED')
