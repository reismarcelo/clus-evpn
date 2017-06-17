#!/bin/bash

id=

while [ $# -gt 0 ]; do
    case "$1" in
        -id)
            id=$2
            shift
            ;;
    esac
    shift
done

if [ -z "${id}" ]; then
cat <<EOF
Vlan Id                             :1
Unicast Octets In                  :0
Unicast Packets In                 :0
Multicast Octets In                :0
Multicast Packets In               :0
Broadcast Octets In                :0
Broadcast Packets In               :0
Unicast Octets Out                 :0
Unicast Packets Out                :0
L3 Unicast Octets In                :0
L3 Unicast Packets In               :0

Vlan Id                             :1001
Unicast Octets In                  :0
Unicast Packets In                 :0
Multicast Octets In                :1624
Multicast Packets In               :0
Broadcast Octets In                :955240
Broadcast Packets In               :0
Unicast Octets Out                 :955240
Unicast Packets Out                :0
L3 Unicast Octets In                :0
L3 Unicast Packets In               :0

Vlan Id                             :1002
Unicast Octets In                  :0
Unicast Packets In                 :0
Multicast Octets In                :0
Multicast Packets In               :0
Broadcast Octets In                :0
Broadcast Packets In               :0
Unicast Octets Out                 :0
Unicast Packets Out                :0
L3 Unicast Octets In                :0
L3 Unicast Packets In               :0
EOF
else
cat <<EOF
Vlan Id                             :${id}
Unicast Octets In                  :0
Unicast Packets In                 :0
Multicast Octets In                :516
Multicast Packets In               :6
Broadcast Octets In                :1980
Broadcast Packets In               :6
Unicast Octets Out                 :0
Unicast Packets Out                :0
L3 Unicast Octets In                :0
L3 Unicast Packets In               :0
EOF
fi
