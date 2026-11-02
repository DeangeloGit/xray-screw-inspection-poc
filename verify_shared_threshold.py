"""Compatibility entry point: shared settings have become per-machine tuning."""
import runpy
runpy.run_module('verify_machine_tuning', run_name='__main__')
