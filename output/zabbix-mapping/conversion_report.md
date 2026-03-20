# 华三监控模板 → Zabbix 转换可行性分析

**生成时间**: 2026-03-20 12:38:46  
**Zabbix 版本**: 7.0.23  
**华三模板总数**: 236

## 转换等级说明

| 等级 | 含义 |
|------|------|
| 🟢 **full** | Zabbix 有对应模板且精确字段匹配率 ≥ 50%，可自动生成大部分 Items 和 Triggers |
| 🟡 **partial** | Zabbix 有对应模板但精确匹配率 < 50%，可生成部分 Items |
| 🔵 **skeleton** | Zabbix 无直接对应模板，但有通用字段匹配（如 CPU、内存），可生成框架 |
| 🔴 **none** | 未归类或华三私有 API，暂无 Zabbix 对应实现 |

## 汇总统计

- 🟢 **full**:    2 个模板
- 🟡 **partial**: 41 个模板
- 🔵 **skeleton**: 193 个模板
- 🔴 **none**:    0 个模板

## 可转换模板明细

| 华三模板名 | 类型 | 等级 | 精确匹配率 | 总匹配率 | 匹配字段 / 总字段 | 可转触发器 | 对应 Zabbix 模板 |
|-----------|------|------|-----------|---------|----------------|-----------|----------------|
| 网络设备 | `network` | 🟢 full | 54% | 54% | 7/13 | 8 | Network Generic Device by SNMP |
| PHP | `php` | 🟢 full | 50% | 50% | 1/2 | 1 | PHP-FPM by HTTP |
| 本地Ping探测 | `pingcmd` | 🟡 partial | 17% | 33% | 2/6 | 1 | ICMP Ping |
| 远程Ping探测 | `ping` | 🟡 partial | 17% | 17% | 1/6 | 1 | ICMP Ping |
| Suse | `suse` | 🟡 partial | 15% | 38% | 15/40 | 1 | Linux by Zabbix agent |
| Etcd | `etcd` | 🟡 partial | 12% | 12% | 1/8 | 1 | Etcd by HTTP |
| Linux | `linux` | 🟡 partial | 12% | 31% | 15/49 | 5 | Linux by Zabbix agent, Linux by Zabbix agent active, Linux by SNMP |
| UOS | `uos` | 🟡 partial | 12% | 31% | 15/49 | 5 | Linux by Zabbix agent |
| 凝思磐石 | `rocky` | 🟡 partial | 12% | 35% | 9/26 | 5 | Linux by Zabbix agent |
| HP-UX | `hpux` | 🟡 partial | 10% | 40% | 8/20 | 3 | HP-UX by Zabbix agent |
| Mac OS | `macos` | 🟡 partial | 10% | 40% | 8/20 | 3 | macOS by Zabbix agent |
| FreeBSD | `freebsd` | 🟡 partial | 10% | 38% | 8/21 | 3 | FreeBSD by Zabbix agent |
| Windows | `winsvr` | 🟡 partial | 9% | 20% | 14/70 | 5 | Windows by Zabbix agent, Windows by Zabbix agent active, Windows by SNMP |
| JavaRuntime | `jrt` | 🟡 partial | 8% | 33% | 4/12 | 1 | Generic Java JMX |
| Apache服务器 | `apache` | 🟡 partial | 8% | 8% | 1/12 | 1 | Apache by HTTP |
| IIS服务器 | `iis` | 🟡 partial | 8% | 38% | 5/13 | 1 | IIS by Zabbix agent |
| Solaris | `solaris` | 🟡 partial | 7% | 39% | 11/28 | 3 | Solaris by Zabbix agent |
| Nginx服务器 | `nginx` | 🟡 partial | 7% | 7% | 1/15 | 1 | Nginx by HTTP, Nginx by Zabbix agent |
| 中标麒麟 | `kylin` | 🟡 partial | 6% | 19% | 9/47 | 5 | Linux by Zabbix agent |
| 银河麒麟 | `kylinos` | 🟡 partial | 6% | 19% | 9/47 | 5 | Linux by Zabbix agent |
| RabbitMQ | `rabbit` | 🟡 partial | 5% | 16% | 3/19 | 1 | RabbitMQ node by HTTP, RabbitMQ cluster by HTTP |
| AIX | `aix` | 🟡 partial | 5% | 33% | 14/43 | 3 | AIX by Zabbix agent |
| MongoDB | `mongo` | 🟡 partial | 4% | 4% | 2/46 | 1 | MongoDB node by Zabbix agent 2 |
| MemCached | `memch` | 🟡 partial | 4% | 8% | 2/25 | 1 | Memcached by Zabbix agent 2 |
| Kafka | `kafka` | 🟡 partial | 4% | 4% | 1/28 | 1 | Apache Kafka by JMX |
| Zookeeper | `zk` | 🟡 partial | 3% | 6% | 2/31 | 1 | Zookeeper by HTTP |
| PostgreSQL | `psql` | 🟡 partial | 2% | 2% | 1/42 | 1 | PostgreSQL by Zabbix agent 2, PostgreSQL by Zabbix agent |
| Redis | `redis` | 🟡 partial | 2% | 2% | 1/41 | 1 | Redis by Zabbix agent 2 |
| Docker | `docker` | 🟡 partial | 2% | 4% | 2/44 | 1 | Docker by Zabbix agent 2 |
| ElasticSearch | `es` | 🟡 partial | 2% | 4% | 2/55 | 1 | Elasticsearch Cluster by HTTP |
| Tomcat服务器 | `tomcat` | 🟡 partial | 2% | 5% | 3/60 | 1 | Apache Tomcat by JMX |
| Brocade | `brocade` | 🟡 partial | 1% | 7% | 5/73 | 1 | Brocade FC by SNMP |
| MySQL | `mysql` | 🟡 partial | 1% | 4% | 3/72 | 1 | MySQL by Zabbix agent 2, MySQL by Zabbix agent |
| MySQL8 | `mysql8` | 🟡 partial | 1% | 3% | 3/89 | 1 | MySQL by Zabbix agent 2 |
| VMware VCenter | `vcenter` | 🟡 partial | 1% | 11% | 11/104 | 1 | VMware |
| Hadoop | `hadoop` | 🟡 partial | 1% | 1% | 1/128 | 1 | Hadoop by HTTP |
| VMware ESX | `vmware` | 🟡 partial | 1% | 9% | 16/170 | 1 | VMware Guest, VMware Hypervisor |
| Kubernetes集群 | `k8s` | 🟡 partial | 0% | 0% | 1/199 | 1 | Kubernetes cluster state by HTTP, Kubernetes nodes by HTTP |
| Kubernetes Master | `kubemaster` | 🟡 partial | 0% | 17% | 5/30 | 0 | Kubernetes API server by HTTP |
| Kubernetes容器 | `kubecon` | 🟡 partial | 0% | 16% | 8/49 | 0 | Kubernetes Kubelet by HTTP |
| Wildfly服务器 | `wildfly` | 🟡 partial | 0% | 10% | 5/52 | 0 | WildFly Server by JMX |
| Oracle | `oracle` | 🟡 partial | 0% | 1% | 2/146 | 0 | Oracle by Zabbix agent 2 |
| SQL Server | `mssql` | 🟡 partial | 0% | 1% | 1/93 | 0 | MSSQL by Zabbix agent 2 |

## 精确字段映射表统计

- 精确映射条目数: **546**
- 覆盖华三类型: **43** 种

## 告警级别对照

| 华三级别 | 华三名称 | Zabbix Severity |
|---------|---------|----------------|
| 1 | 提示 | INFO |
| 2 | 一般 | WARNING |
| 3 | 次要 | AVERAGE |
| 4 | 重要 | HIGH |
| 5 | 紧急 | DISASTER |

## 告警运算符对照

| 华三运算符 | 含义 | Zabbix 表达式 |
|-----------|------|-------------|
| `GT` | | `>` |
| `GE` | | `>=` |
| `LT` | | `<` |
| `LE` | | `<=` |
| `EQ` | | `=` |
| `NEQ` | | `<>` |
| `IC` | | `like` |
| `EC` | | `not like` |
| `RULE` | | `regexp` |
| `CHG` | | `change` |
| `CT` | | `>=` |
| `DC` | | `<=` |

## 骨架模板（skeleton）

以下模板 Zabbix 无直接对应，但有通用指标（CPU/内存等）字段匹配，可生成监控框架：

| 华三模板名 | 类型 | 匹配字段数 |
|-----------|------|-----------|
| HW FusionCompute | `hwfc` | 28 |
| CloudOS7 | `cloudos7` | 24 |
| UIS | `uis` | 18 |
| NEW CAS集群 | `newcas` | 17 |
| 绿洲平台 | `oasis` | 12 |
| KVM | `kvm` | 12 |
| 简云 | `lc` | 12 |
| Citrix XenServer | `citrix` | 10 |
| CloudOS | `cloudos` | 10 |
| CloudOS MQS | `mqs` | 9 |
| CAS集群 | `cas` | 9 |
| H3C DataX | `dx` | 8 |
| H3C Workspace | `h3c_vdi` | 8 |
| OpenBSD | `openbsd` | 8 |
| SCO UNIX | `sco_sv` | 8 |
| HyperV | `hyperv` | 8 |
| 傲飞算力平台 | `ampha` | 7 |
| HBase | `hbase` | 7 |
| Storm | `storm` | 7 |
| H3C UniStor CT3000 | `h3cunistorct3000` | 7 |
| TAP8000-SDN | `tapsdn` | 6 |
| ActiveMQ | `amq` | 6 |
| Jetty | `jetty` | 6 |
| Lotus Domino 服务器 | `lotus` | 6 |
| Lync 2013 服务器 | `lync13` | 6 |
| 工业操作系统物联开发套件 | `h3cdicp` | 5 |
| H3C SecPath SSMS | `ssmsser` | 5 |
| 金蝶服务器 | `apusic` | 5 |
| H3C SecPath 密码服务中间件 | `cp8000` | 4 |
| H3C SecPath ISG-MGT | `isgmgt` | 4 |
| H3C SecPath 密钥管理系统 | `kms8000` | 4 |
| SeaSQL DRDS | `drds` | 4 |
| Exchange 2010 | `ex10` | 4 |
| Exchange 2016 | `ex16` | 4 |
| TongLINK/Q | `tonglq` | 4 |
| HW OceanStor 5800 V3 | `hw5800v3` | 4 |
| H3C ONEStor | `onestor` | 4 |
| H3C P5730 | `p5730` | 4 |
| Active Directory服务 | `ad` | 3 |
| H3C CSAP-WEB监测扫描系统 | `csapwmc` | 3 |
| 绿洲应用开发平台 | `h3cadp` | 3 |
| 工业操作系统应用支持套件 | `h3ciitapp` | 3 |
| 工业操作系统模型开发套件 | `h3ciitmodel` | 3 |
| 绿洲融合集成平台 | `h3coip` | 3 |
| 南大通用数据库 | `gbase` | 3 |
| Oracle ASM | `oasm` | 3 |
| .NET服务器 | `dotnet` | 3 |
| Resin | `resin` | 3 |
| Solr服务器 | `solr` | 3 |
| H3C Blade Server | `h3c_blade_server` | 3 |
| UNIS Blade Server | `unis_blade_server` | 3 |
| DELL EqualLogic | `equallogic` | 3 |
| 华为通用存储 | `hw18500v1` | 3 |
| HW OceanStor 5300V3 | `hw5300v3` | 3 |
| H3C UniStor X10000 | `nasx1w` | 3 |
| H3C UniStor X10000C/T/H | `nasx1wt` | 3 |
| NetApp AFF A700 | `neta700` | 3 |
| NetApp | `netapp` | 3 |
| UNISINSIGHT | `unisit` | 3 |
| UNIS X10216 | `ux10216` | 3 |
| 综合日志审计平台 | `clap` | 2 |
| H3C 百业灵犀 | `h3clinseer` | 2 |
| H3C SecCenter ESM | `esm` | 2 |
| NDR | `ndr` | 2 |
| 安全业务管理平台 | `smp` | 2 |
| 安全威胁发现与运营管理平台 | `tdsop` | 2 |
| NVIDIA GPU | `nvidia_gpu` | 2 |
| 天数智芯 GPU | `iluvatar_corex_gpu` | 2 |
| SAP HANA | `hana` | 2 |
| SeaSQL MPP | `ssm` | 2 |
| Sybase | `sybase` | 2 |
| 虚谷数据库 | `xugu` | 2 |
| 东方通服务器 | `tongweb` | 2 |
| Tuxedo | `tuxedo` | 2 |
| H3C UniStor CD | `h3ccd` | 2 |
| 昆腾 Scalar i500 | `kti500` | 2 |
| UNIS XC20000 | `unisxc20000` | 2 |
| ACG Manager | `acg` | 1 |
| ACG BA | `acgba` | 1 |
| Ceph | `ceph` | 1 |
| WBC云简平台 | `h3cwbc` | 1 |
| H3C人工智能平台 | `cloudai` | 1 |
| Linux自定义 | `custcmd` | 1 |
| 目录 | `dir` | 1 |
| DNS服务 | `dns` | 1 |
| 文件 | `file` | 1 |
| 绿洲数据运营平台 | `h3codop` | 1 |
| H3C 物联网平台2.0 | `h3cwlw` | 1 |
| 工业治理平台 | `idgp` | 1 |
| 工业操作系统 | `iiotos` | 1 |
| H3C SecPath 工控主机安全卫士 | `isgimw` | 1 |
| LDAP 服务 | `ldap` | 1 |
| 远程URL探测 | `lr_curl` | 1 |
| 远程Netcat探测 | `lr_nc` | 1 |
| 远程Telnet探测 | `lr_telnet` | 1 |
| H3C安全云管理平台 | `seccloud` | 1 |
| H3C SecPath SSMS-Cloud | `ssms` | 1 |
| TCP Port | `tcpport` | 1 |
| URL | `url` | 1 |
| 零信任访问控制系统 | `ztna` | 1 |
| Cache | `cache` | 1 |
| Cache 2010 | `cache2010` | 1 |
| CloudOS DBaaS | `codbaas` | 1 |
| 绿洲大数据平台 | `datange` | 1 |
| DB2 | `db2` | 1 |
| DB2 DPF | `db2dpf` | 1 |
| DB2 v11 | `db2v11` | 1 |
| 达梦数据库 | `dm` | 1 |
| Informix | `ifx` | 1 |
| 金仓数据库 | `king` | 1 |
| 金仓V8数据库 | `king8` | 1 |
| Oracle PDB | `oraclepdb` | 1 |
| 神通 | `st` | 1 |
| Flume | `flume` | 1 |
| GlassFish服务器 | `gf` | 1 |
| H3C SDN | `h3csdn` | 1 |
| JBoss服务器 | `jboss` | 1 |
| Oracle GoldenGate | `ogg` | 1 |
| POP3 | `pop3` | 1 |
| SMTP | `smtp` | 1 |
| WebLogic服务器 | `wl` | 1 |
| WebSphere MQ | `wmq` | 1 |
| WebSphere服务器 | `ws` | 1 |
| ChinaTelecom Server | `chinatelecom_server` | 1 |
| CISCO Server | `cisco_server` | 1 |
| Dell Blade Server | `dell_blade_server` | 1 |
| Dell Server | `dell_server` | 1 |
| Enflame Server | `enflame_server` | 1 |
| H3C Server | `h3c_server` | 1 |
| HP Blade Server | `hp_blade_server` | 1 |
| HP Integrity Server | `hp_integrity_server` | 1 |
| HP Server | `hp_server` | 1 |
| HUAWEI Blade Server | `huawei_blade_server` | 1 |
| HUAWEI Server | `hw_server` | 1 |
| IBM Server | `ibm_server` | 1 |
| i2Box Server | `information2_server` | 1 |
| INSPUR Server | `inspur_server` | 1 |
| Lenovo Server | `lenovo_server` | 1 |
| Resolink Server | `resolink_server` | 1 |
| Sugon Server | `sugon_server` | 1 |
| UNIS Server | `unis_server` | 1 |
| Unisit Server | `unisit_server` | 1 |
| XSKY Server | `xsky_server` | 1 |
| ZTE Server | `zte_server` | 1 |
| 浪潮 AS5600 | `as5600` | 1 |
| H3C UniStor CB | `cba1106` | 1 |
| H3C UniStor CF2000 | `cf2205` | 1 |
| 通用存储设备 | `comsto` | 1 |
| H3C UniStor CX2000N | `cx2000n` | 1 |
| DELL Storage Center 2020 | `dellsc2020` | 1 |
| DELL EMC SC4020 | `dls4020` | 1 |
| DELL EMC SC5020 | `dls5020` | 1 |
| EMC ISILON | `emc_isilon` | 1 |
| EMC CLARiiON | `emcclar` | 1 |
| EMC VMAX 100K | `emcvmx` | 1 |
| H3C UniStor CB7000 | `h3ccb7000` | 1 |
| H3C UniStor CB7000_CDP | `h3ccb7000cdp` | 1 |
| H3C UniStor CB7000 V3 | `h3ccb7000v3` | 1 |
| H3C UniStor CF22000 | `h3ccf22000` | 1 |
| H3C UniStor CF22000H | `h3ccf22000h` | 1 |
| H3C UniStor CF5000 | `h3ccf5040` | 1 |
| H3C UniStor CF6000 | `h3ccf6000` | 1 |
| H3C UniStor CF8850H | `h3ccf8850h` | 1 |
| H3C UniStor CH3800 | `h3cch3800` | 1 |
| H3C UniStor CP | `h3ccp5520` | 1 |
| H3C UniStor CX | `h3ccxseries` | 1 |
| HPE 3PAR | `hp3par` | 1 |
| HPE Nimble HF40 | `hphf40` | 1 |
| HPE MSA2050 | `hpm2050` | 1 |
| HP Primera | `hpprim` | 1 |
| HPE StoreOnce 5200 | `hps5200` | 1 |
| HUS110 | `hus110` | 1 |
| HW OceanStor 18500 V3 | `hw18500` | 1 |
| 华为T系列 | `hw5600tv1` | 1 |
| HW OceanStor 9000 | `hw9000` | 1 |
| HW OceanStor S3900 | `hws3900` | 1 |
| IBM DS系列 | `ibmds` | 1 |
| IBM DS8800 | `ibmds8800` | 1 |
| IBM F900 | `ibmf900` | 1 |
| IBM FlashSystem系列 | `ibmfs` | 1 |
| IBM SVC | `ibmsvc` | 1 |
| IBM Storwize V系列 | `ibmv7k` | 1 |
| 宏杉 MS5520 | `ms5520` | 1 |
| HP MSA P2000 | `msap2k` | 1 |
| H3C ONEStor3.0 | `onest3` | 1 |
| DELL SC 8000 | `sc8k` | 1 |
| EMC VNX5300 | `vnx5300` | 1 |
| EMC VPLEX | `vplex` | 1 |
| VMWare VSAN | `vsan` | 1 |
| Hitachi VSP | `vsp` | 1 |
| VSP G200 | `vspg200` | 1 |
| ZTE KS3200 | `zteks3200` | 1 |
| 测试服务器模板 | `dell_server` | 1 |