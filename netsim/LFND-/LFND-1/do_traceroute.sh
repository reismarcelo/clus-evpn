#!/bin/bash

if [ "$1" == "172.16.1.1" -a "$2" == "vrf"  -a "$3" == "management" ]; then

cat <<EOF
traceroute to 172.16.1.1 (172.16.1.1), 30 hops max, 40 byte packets
 1  172.16.1.1 (172.16.1.1)  1.245 ms  0.88 ms  0.753 ms
EOF

else
cat <<EOF
Access to this hostname/IP address is not permitted
EOF

fi
