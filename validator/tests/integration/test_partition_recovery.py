# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------
import copy
import logging
import math
import os
import time
import traceback
import unittest

from txnintegration.netconfig import NetworkConfig
from txnintegration.matrices import NopEdgeController
from txnintegration.validator_network_manager import ValidatorNetworkManager
from txnintegration.validator_collection_controller import \
    ValidatorCollectionController
from txnintegration.integer_key_client import IntegerKeyClient
from txnintegration.utils import is_convergent
from txnintegration.utils import sit_rep
from txnintegration.utils import generate_private_key as gen_pk


logger = logging.getLogger(__name__)

ENABLE_INTEGRATION_TESTS = False
if os.environ.get("ENABLE_INTEGRATION_TESTS", False) == "1":
    ENABLE_INTEGRATION_TESTS = True


class TestPartitionRecovery(unittest.TestCase):
    def _do_work(self, ik_client, off, n_mag):
        for i in range(off, off + n_mag):
            ik_client.set(key=str(i), value=math.pow(2, i))
            ik_client.waitforcommit()

    @unittest.skip("temporarily disabling")
    @unittest.skipUnless(ENABLE_INTEGRATION_TESTS, "integration test")
    def test_two_clique(self):
        # this topology forms 2 exclusive cliques when n2 is severed
        vulnerable_mat = [
            [1, 1, 0, 0, 0],
            [1, 1, 1, 0, 0],
            [0, 1, 1, 1, 0],
            [0, 0, 1, 1, 1],
            [0, 0, 0, 1, 1],
        ]
        two_clique_mat = copy.deepcopy(vulnerable_mat)
        two_clique_mat[2][2] = 0
        n = len(vulnerable_mat)
        vnm = ValidatorNetworkManager(n)
        print
        try:
            print 'phase 0: build vulnerably connected 5-net:'
            from txnintegration.netconfig import NetworkConfigProvider
            provider = NetworkConfigProvider()
            net_cfg = NetworkConfig(n, provider=provider)
            net_cfg.set_nodes(vulnerable_mat)
            net_cfg.set_peers(vulnerable_mat)
            net_cfg.set_blacklist()
            vcc = ValidatorCollectionController(net_cfg)
            vnm.initialize(net_cfg, vcc, NopEdgeController(net_cfg))
            print 'phase 1: launch vulnerably connected 5-net:'
            vnm.do_genesis(probe_seconds=0)
            vnm.launch(probe_seconds=0)
            print 'phase 2: validate state across 5-net:'
            sit_rep(vnm.urls(), verbosity=2)
            print 'phase 3: morph 5-net into two exclusive 2-net cliques:'
            vnm.update(node_mat=two_clique_mat, probe_seconds=0, reg_seconds=0)
            print 'providing time for convergence (likely partial)...'
            time.sleep(32)
            sit_rep(vnm.urls())
            print 'phase 4: generate chain-ext A on clique {0, 1}:'
            url = vnm.urls()[0]
            print 'sending transactions to %s...' % (url)
            ikcA = IntegerKeyClient(baseurl=url, keystring=gen_pk())
            self._do_work(ikcA, 5, 2)
            print 'providing time for partial convergence...'
            time.sleep(8)
            sit_rep(vnm.urls())
            print 'phase 5: generate chain-ext B on clique {3, 4}, |B| = 2|A|:'
            url = vnm.urls()[-1]
            print 'sending transactions to %s...' % (url)
            ikcB = IntegerKeyClient(baseurl=url, keystring=gen_pk())
            self._do_work(ikcB, 1, 4)
            print 'providing time for partial convergence...'
            time.sleep(8)
            sit_rep(vnm.urls())
            print 'TEST 1: asserting network is forked'
            self.assertEquals(False, is_convergent(vnm.urls(), standard=3))
            print 'phase 6: reconnect 5-net:'
            print 'rezzing validator-2 with InitialConnectivity = |Peers|...'
            cfg = vnm.get_configuration(2)
            cfg['InitialConnectivity'] = 2
            vnm.set_configuration(2, cfg)
            vnm.update(node_mat=vulnerable_mat, probe_seconds=0, reg_seconds=0)
            print 'phase 7: validate state across 5-net:'
            print 'providing time for global convergence...'
            time.sleep(64)
            sit_rep(vnm.urls())
            print 'TEST 2: asserting network is convergent'
            self.assertEquals(True, is_convergent(vnm.urls(), standard=4))
        except Exception as e:
            print 'Exception encountered: %s' % (e.message)
            traceback.print_exc()
            sit_rep(vnm.urls())
            raise
        finally:
            vnm.shutdown(archive_name="TestPartitionRecoveryResults")
