#!/bin/bash

if [ "$1" = "" ]; then
cat <<EOF
tb3-tor1# show nve vni
Codes: CP - Control Plane        DP - Data Plane          
       UC - Unconfigured         SA - Suppress ARP
       
Interface VNI      Multicast-group   State Mode Type [BD/VRF]      Flags
--------- -------- ----------------- ----- ---- ------------------ -----
nve1      52004    224.1.1.255       Up    CP   L2 [1003]               
nve2      52005    224.1.1.255       Up    CP   L2 [1003]               
EOF
else
cat <<EOF
VNI: $1
TX
        8370 unicast packets 955240 unicast bytes
        0 multicast packets 0 multicast bytes
RX
        0 unicast packets 0 unicast bytes
        8382 multicast packets 956864 multicast bytes
EOF
fi
