FROM oven/bun:1-alpine AS base

FROM base AS builder

# Use USTC mirror for faster/offline-friendly apk downloads
RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.ustc.edu.cn|g' /etc/apk/repositories

RUN apk add --no-cache \
    net-snmp \
    net-snmp-tools \
    net-snmp-libs \
    bash \
    curl \
    procps \
    && mkdir -p /usr/share/snmp/mibs \
    && mkdir -p /var/lib/net-snmp \
    && mkdir -p /var/run/net-snmp

# Copy custom snmpd configuration
COPY snmpd.conf /etc/snmp/snmpd.conf
COPY snmpd-extend.sh /usr/local/bin/snmpd-extend.sh
COPY pp_h3c.sh /usr/local/bin/pp_h3c.sh
COPY pp_entity.sh /usr/local/bin/pp_entity.sh
COPY snmp_pass_h3c.sh /usr/local/bin/snmp_pass_h3c.sh
COPY snmp_pass_entity.sh /usr/local/bin/snmp_pass_entity.sh
RUN chmod +x /usr/local/bin/snmpd-extend.sh \
    /usr/local/bin/pp_h3c.sh \
    /usr/local/bin/pp_entity.sh \
    /usr/local/bin/snmp_pass_h3c.sh \
    /usr/local/bin/snmp_pass_entity.sh

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# SNMP default port
EXPOSE 161/udp
EXPOSE 162/udp

ENTRYPOINT ["/entrypoint.sh"]
