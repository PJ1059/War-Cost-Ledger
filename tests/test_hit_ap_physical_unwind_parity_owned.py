"""One pure focused scope check; native owned run is a separate explicit call."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_new_parity_scope',ROOT/'tools/native/hit_ap_physical_unwind_parity_owned.py')
wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)


class NewParityScopeTests(unittest.TestCase):
    def test_only_new_saved_instruction_boundaries_and_fixed28_RF_reuse(self):
        code,_=wrapper.mapper.code_copy.load_sources();pcs,evidence=wrapper.load_pcs(code)
        self.assertEqual(tuple(pcs),tuple(wrapper.mapper.code_copy.REGIONS))
        self.assertEqual({name:pcs[name]for name in wrapper.NOT_RETESTED},
                         {name:[]for name in wrapper.NOT_RETESTED})
        self.assertEqual({row['region']for row in evidence},set(wrapper.TEST_REGIONS))
        for name in wrapper.TEST_REGIONS:
            begin,_,length=wrapper.mapper.code_copy.REGIONS[name]
            self.assertGreater(len(pcs[name]),0);self.assertEqual(len(set(pcs[name])),len(pcs[name]))
            self.assertEqual(min(pcs[name]),begin);self.assertLess(max(pcs[name]),begin+length)
        self.assertEqual(wrapper.mapper.RF_COUNT,28)
        self.assertEqual(wrapper.run_source.count('RuntimeFunction * mapper.RF_COUNT'),2)
        self.assertNotIn('RuntimeFunction * 19',wrapper.run_source)
        self.assertIn("report['runtime_function_count'] = mapper.RF_COUNT",wrapper.run_source)
        self.assertIn('nt.RtlVirtualUnwind(0, base, control_pc',wrapper.run_source)
        self.assertIn('stack + 0x8000',wrapper.run_source)
        self.assertNotIn('RtlAddFunctionTable',wrapper.run_source)
        self.assertIn('memory.close()',wrapper.run_source)
        self.assertFalse(any(row['normal_CFG_closed_proven']for row in evidence))
        print('NEW_PARITY_SCOPE_PASS counts='+str({n:len(pcs[n])for n in pcs})+' Windows_API_called=false Game_accessed=false')


if __name__=='__main__':unittest.main()
