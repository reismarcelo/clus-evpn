""" CLUS-EVPN - NSO EVPN project for Cisco Live US 2017
"""
from __future__ import absolute_import, division, print_function
from builtins import (ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round,
                      super, zip)
from builtins import str as text
import ncs
from ncs.application import Service
import ncs.template
from vxlan.utils import apply_template, NcsServiceConfigError, value_or_empty, get_device_asn


# ------------------------------------
# L2 VXLAN TOPOLOGY SERVICE CALLBACK
# ------------------------------------
class VxlanL2ServiceCallback(Service):
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info('Service create(service={})'.format(service))

        for leaf in service.ports.leaf_node:
            self.log.info('Rendering L2 leaf template for {}'.format(leaf.node_name))
            apply_template('l2_leaf_node', service.ports.leaf_node[leaf.node_name])

        if len(service.dci.vlan) != len(root.plant_information.plant[service.dc_name].border_leaf_node):
            raise NcsServiceConfigError('Number of L2 DCI VLANs must match the number of border-leaf nodes')

        for border_leaf, dci_vlan in zip(root.plant_information.plant[service.dc_name].border_leaf_node,
                                         service.dci.vlan):
            self.log.info('Rendering L2 border-leaf template for {}'.format(border_leaf.name))
            border_leaf_vars = {
                'DEVICE': border_leaf.name,
                'DCI_VLAN': dci_vlan.id,
                'DCI_VLAN_NAME': dci_vlan.name
            }
            apply_template('l2_border_leaf_node', service, border_leaf_vars)

            self.log.info('Rendering border-leaf vlan template for {}'.format(border_leaf.name))
            dci_ports = border_leaf.dci_layer2.interface.Port_channel or border_leaf.dci_layer2.interface.Ethernet
            if len(dci_ports) != 1:
                raise NcsServiceConfigError('Each border-leaf can only have one L2 DCI port')
            for dci_port in dci_ports:
                border_leaf_vlan_vars = {
                    'DCI_PORT': dci_port.id,
                }
                border_leaf_vlan_vars.update(border_leaf_vars)
                apply_template('border_leaf_node_vlans', dci_port, border_leaf_vlan_vars)


# ------------------------------------
# L3 VXLAN TOPOLOGY SERVICE CALLBACK
# ------------------------------------
class VxlanL3ServiceCallback(Service):
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info('Service create(service={})'.format(service))

        common_vars = {
            'PREFIX-TAG': value_or_empty(root.plant_information.global_config.tenant_prefix_tag),
            'REDIST-STATIC': value_or_empty(root.plant_information.global_config.tenant_route_maps.bgp_redistribute_static),
            'REDIST-CONNECTED': value_or_empty(root.plant_information.global_config.tenant_route_maps.bgp_redistribute_connected),
        }

        for leaf in service.ports.leaf_node:
            self.log.info('Rendering L3 leaf template for {}'.format(leaf.node_name))

            leaf_vars = {
                'DEVICE-ASN': get_device_asn(root, leaf.node_name),
            }
            leaf_vars.update(common_vars)
            apply_template('l3_leaf_node', service.ports.leaf_node[leaf.node_name], leaf_vars)

        dci_vlans = [vlan.id for vlan in service.dci.vlan]

        for border_leaf in root.plant_information.plant[service.dc_name].border_leaf_node:
            self.log.info('Rendering L3 border-leaf template for {}'.format(border_leaf.name))
            border_leaf_vars = {
                'DEVICE': border_leaf.name,
                'DEVICE-ASN': get_device_asn(root, border_leaf.name),
            }
            border_leaf_vars.update(common_vars)
            apply_template('l3_border_leaf_node', service, border_leaf_vars)

            self.log.info('Rendering border-leaf vlan template for {}'.format(border_leaf.name))
            dci_ports = border_leaf.dci_layer3.interface.Port_channel or border_leaf.dci_layer3.interface.Ethernet
            if len(dci_ports) != len(dci_vlans):
                raise NcsServiceConfigError('Number of DCI VLANs must match number of L3 DCI ports')
            for dci_port, dci_vlan in zip(dci_ports, dci_vlans):
                border_leaf_vlan_vars = {
                    'DEVICE': border_leaf.name,
                    'DCI_PORT': dci_port.id,
                    'DCI_VLAN': dci_vlan,
                }
                apply_template('border_leaf_node_vlans', dci_port, border_leaf_vlan_vars)


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



