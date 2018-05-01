""" CLUS-EVPN - NSO EVPN project for Cisco Live US 2017
"""
from __future__ import absolute_import, division, print_function
from builtins import (ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round,
                      super, zip)
from builtins import str as text
import ncs
from ncs.application import Service
import ncs.template
from vxlan.utils import apply_template, NcsServiceError, value_or_empty, get_device_asn, plan_data_service


# ------------------------------------
# L2 VXLAN TOPOLOGY SERVICE CALLBACK
# ------------------------------------
class VxlanL2ServiceCallback(Service):
    @Service.create
    @plan_data_service()
    def cb_create(self, tctx, root, service, proplist, self_plan):
        common_vars = {
            'NVE_SOURCE': value_or_empty(root.plant_information.global_config.nve_source_interface),
        }

        # Process leaf nodes
        self.log.info('Rendering L2 leaf template')
        apply_template('l2_leaf_node', service, common_vars)

        # Process border-leaf nodes
        border_leaf_nodes = root.plant_information.plant[service.dc_name].border_leaf_node
        dci_vlans = [vlan for vlan in service.dci.vlan]

        if not ((len(dci_vlans) == 1) or (len(dci_vlans) == len(border_leaf_nodes))):
            raise NcsServiceError('Number of L2 DCI VLANs must be either 1 or match the number of border-leaf nodes')

        for b_leaf, b_leaf_dci_vlans in zip(border_leaf_nodes, split_l2_dci_vlans(dci_vlans)):

            if num_dci_ports(b_leaf.dci_layer2) != 1:
                raise NcsServiceError('Each border-leaf can only have one L2 DCI port. ')

            b_leaf_info = service.border_leaf_info.create(b_leaf.name)
            fill_border_leaf_info(b_leaf_info, b_leaf.dci_layer2, b_leaf_dci_vlans)

        self.log.info('Rendering L2 border-leaf template')
        apply_template('l2_border_leaf_node', service, common_vars)

        return proplist


def split_l2_dci_vlans(vlan_list):
    """
    Assign Layer2 DCI VLANs to border-leafs. Returns an unbounded generator that yields each element of vlan_list,
    then keep returning the last element once vlan_list is exhausted.

    :param vlan_list: A list of VLANs to be split
    :return: A generator that yields lists containing one VLAN
    """
    for i in range(len(vlan_list)):
        yield vlan_list[i:i+1]
    while True:
        yield vlan_list[-1::]


# ------------------------------------
# L3 VXLAN TOPOLOGY SERVICE CALLBACK
# ------------------------------------
class VxlanL3ServiceCallback(Service):
    @Service.create
    @plan_data_service()
    def cb_create(self, tctx, root, service, proplist, self_plan):
        common_vars = {
            'NVE_SOURCE': value_or_empty(root.plant_information.global_config.nve_source_interface),
            'PREFIX-TAG': value_or_empty(root.plant_information.global_config.tenant_prefix_tag),
            'REDIST-STATIC': value_or_empty(root.plant_information.global_config.tenant_route_maps.bgp_redistribute_static),
            'REDIST-CONNECTED': value_or_empty(root.plant_information.global_config.tenant_route_maps.bgp_redistribute_connected),
        }

        # Process leaf nodes
        self.log.info('Rendering L3 leaf template')
        apply_template('l3_leaf_node', service, common_vars)

        # Process border-leaf nodes
        border_leaf_nodes = root.plant_information.plant[service.dc_name].border_leaf_node
        dci_vlans = [vlan for vlan in service.dci.vlan]

        if len(dci_vlans) % len(border_leaf_nodes) != 0:
            raise NcsServiceError('Number of DCI VLANs must be divisible by the number of border-leaf nodes')

        for b_leaf, b_leaf_dci_vlans in zip(border_leaf_nodes, split_l3_dci_vlans(dci_vlans, len(border_leaf_nodes))):

            if num_dci_ports(b_leaf.dci_layer3) != len(b_leaf_dci_vlans):
                raise NcsServiceError('Border-leaf number of L3 DCI ports does not match number of DCI VLANs.')

            b_leaf_info = service.border_leaf_info.create(b_leaf.name)
            fill_border_leaf_info(b_leaf_info, b_leaf.dci_layer3, b_leaf_dci_vlans)

        self.log.info('Rendering L3 border-leaf template')
        apply_template('l3_border_leaf_node', service, common_vars)

        return proplist


def split_l3_dci_vlans(vlan_list, num_border_leaf):
    """
    Assign Layer3 DCI VLANs to border-leafs. Returns a generator that yields a list of DCI VLANs for being used at
    a border-leaf.
    VLANs are assigned to border-leafs in sequence by border-leaf:
    Given vlan_list = [1001, 1002, 1003, 1004]
    First border-leaf gets [1001, 1003], second gets [1002, 1004]

    :param vlan_list: A list of VLANs to be split
    :param num_border_leaf: Number of border-leaf nodes
    :return: A generator that yields lists containing DCI VLANs for the border-leaf node
    """
    return (vlan_list[i::num_border_leaf] for i in range(num_border_leaf))


def num_dci_ports(border_leaf_dci):
    return len(border_leaf_dci.interface.Port_channel or border_leaf_dci.interface.Ethernet)


def fill_border_leaf_info(border_leaf_info_node, dci_ports, dci_vlans):
    for src_port_channel, dst_port_channel, dci_vlan in copy_zip_list('id',
                                                                      dci_ports.interface.Port_channel,
                                                                      border_leaf_info_node.interface.Port_channel,
                                                                      dci_vlans):
        dst_port_channel.vlan_id = dci_vlan.id
        dst_port_channel.vlan_name = dci_vlan.name
        copy_zip_list('member_id', src_port_channel.members.Ethernet, dst_port_channel.members.Ethernet)
    for src_ethernet, dst_ethernet, dci_vlan in copy_zip_list('id',
                                                              dci_ports.interface.Ethernet,
                                                              border_leaf_info_node.interface.Ethernet,
                                                              dci_vlans):
        dst_ethernet.vlan_id = dci_vlan.id
        dst_ethernet.vlan_name = dci_vlan.name


def copy_zip_list(key, src_list, dst_list, *extra_lists):
    for item in src_list:
        dst_list.create(getattr(item, key))
    return zip(src_list, dst_list, *extra_lists)


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(ncs.application.Application):
    def setup(self):
        self.log.info('VXLAN Service RUNNING')

        # Registration of service callbacks
        self.register_service('vxlan-l2-servicepoint', VxlanL2ServiceCallback)
        self.register_service('vxlan-l3-servicepoint', VxlanL3ServiceCallback)

    def teardown(self):
        self.log.info('VXLAN Service FINISHED')



