#!/bin/bash

if [ "$1" == "172.16.1.1" -a "$2" == "vrf"  -a "$3" == "management" ]; then

cat <<EOF
PING 172.16.1.1 (172.16.1.1): 56 data bytes
64 bytes from 172.16.1.1: icmp_seq=0 ttl=63 time=1.287 ms
64 bytes from 172.16.1.1: icmp_seq=1 ttl=63 time=1.609 ms
64 bytes from 172.16.1.1: icmp_seq=2 ttl=63 time=0.777 ms
64 bytes from 172.16.1.1: icmp_seq=3 ttl=63 time=0.776 ms
64 bytes from 172.16.1.1: icmp_seq=4 ttl=63 time=1.246 ms

--- 172.16.1.1 ping statistics ---
5 packets transmitted, 5 packets received, 0.00% packet loss
round-trip min/avg/max = 0.776/1.139/1.609 ms
EOF

else
cat <<EOF
Access to this hostname/IP address is not permitted
EOF

fi
