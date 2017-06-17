#!/bin/sh
# note that this script is for backwards compatibility only
# it is not used by ncs-netsim cli command
. ./env.sh 
${CONFD_DIR}/bin/confd_cli -u admin -J ${CONFD_CLI_FLAGS}
