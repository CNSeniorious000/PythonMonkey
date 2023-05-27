# @file         require.py
#               Implementation of CommonJS "require" for PythonMonkey. This implementation uses the
#               ctx-module npm package to do the heavy lifting. That package makes a complete module
#               system, obstensibly in a separate context, but our implementation here reuses the
#               PythonMonkey global context for both.
#
#               The context that ctx-module runs in needs a require function supporting
#                - require('debug') => returns a debug function which prints to the console when
#                                      debugging; see the node debug built-in
#                - require('fs')    => returns an object which has an implementation of readFileSync
#                                      and statSync. The implementation of statSync only needs to
#                                      return the mode member. The fs module also needs
#                                      constants.S_IFDIR available.
#                - require('vm')    => returns an object which has an implementation of evalInContext
#
#               In order to implement this basic require function for bootstrapping ctxModule, we
#               have simply made global variables of the form xxxModule where xxx is the module
#               identifier, and injected a require function which understands this. A better
#               implementation in Python that doesn't leak global symbols should be possible once
#               some PythonMonkey bugs are fixed.
#
# @author       Wes Garland, wes@distributive.network
# @date         May 2023
#

import sys
sys.path.append(path.dirname(__file__) + '/build/src');

import pythonmonkey as pm
from os import stat, path, getcwd
    
pm.eval("globalThis.vmModule = { runInContext: eval }; true")
pm.eval("globalThis.require = function outerRequire(mid) { const module = globalThis[mid + 'Module']; if (module) return module; throw new Error('module not found: ' + mid) }");
pm.eval("globalThis.debugModule = function debug() { return function debugInner() { debugPrint('DEBUG: ' + Array.from(arguments).join(' ')) }}; true");
globalSet = pm.eval('(function globalSet(name, prop) { globalThis[name] = prop; })')
propSet = pm.eval('(function propSet(objName, propName, propValue) { globalThis[objName] = globalThis[objName] || {}; globalThis[objName][propName] = propValue; })')

# Make global.debugPrint equivalent to Python's print() function
globalSet('debugPrint', print);

# Implement enough of require('fs') so that ctx-module can find/load files
def statSync_inner(filename):
    if (path.exists(filename)):
        sb = stat(filename)
        return { 'mode': 0 }
    else:
        return False

def readFileSync(filename, charset):
    fileHnd = open(filename, "r")
    return fileHnd.read()

propSet('fsModule', 'statSync_inner', statSync_inner);
propSet('fsModule', 'readFileSync', readFileSync)
propSet('fsModule', 'existsSync', path.exists)
pm.eval("fsModule.constants = { S_IFDIR: 16384 }; true;")
pm.eval("""fsModule.statSync =
function statSync(filename)
{
  const ret = require('fs').statSync_inner(filename);
  if (ret)
    return ret;

  const err = new Error('file not found: ' + filename); 
  err.code='ENOENT'; 
  throw err;
}""");

# Read in ctx-module and invoke so that this file is the "main module" and the Python symbol require is
# now the corresponding CommonJS require() function.  We use the globalThis as the module's exports
# because PythonMonkey current segfaults when return objects. Once that is fixed, we will pass moduleIIFE
# parameters which are a python implementation of top-level require(for fs, vm - see top) and an exports
# dict to decorate.
ctxModuleSource = open(path.dirname(__file__) + "/node_modules/ctx-module/ctx-module.js", "r")
moduleWrapper = pm.eval("""'use strict';
(function moduleWrapper(require, exports)
{
  exports=exports || globalThis; 
  require=require || globalThis.require;
""" + ctxModuleSource.read() + """
})
""");

# inject require and exports symbols as moduleWrapper arguments once jsObj->dict fixed so we don't have
# to use globalThis and pollute the global scope. 
moduleWrapper()

# __builtinModules should be a dict that we add built-in modules to in Python, then pass the same
# dict->jsObject in createRequire for every require we create.
pm.eval('const __builtinModules = {}; true');

# API - createRequire
# returns a require function which returns a require function that resolves modules relative to the
# filename argument. Conceptually the same as node:module.createRequire().
#
# example:
#   from pythonmonkey import createRequire
#   require = createRequire(__file__)
#   require('./my-module')
#
def createRequire(filename):
    import pythonmonkey as pm
    return (pm.eval("((new CtxModule(globalThis, '" + filename + "', __builtinModules)).require)"))