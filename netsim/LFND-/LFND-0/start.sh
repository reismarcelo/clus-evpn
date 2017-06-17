#!/bin/sh
. ./env.sh 
env sname=${NAME} ${CONFD} -c confd.conf --addloadpath  ${CONFD_DIR}/etc/confd ${CONFD_FLAGS}
