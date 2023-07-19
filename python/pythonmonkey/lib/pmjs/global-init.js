/**
 * @file        global-init.js
 *              Set up global scope which is used to run either program or REPL code in the pmjs script
 *              runner.
 *
 * @author      Wes Garland, wes@distributive.network
 * @date        June 2023
 */
'use strict';

/* Anything loaded with require() before the program started was a side effect and not part of the 
 * program. This means that by now, whoever needed the resources should have memoized them someplace
 * safe, and we can remove them to keep the namespace clean.
 */
for (let mid in require.cache)
  delete require.cache[mid];

exports.prepareEventLoop = function globalInit$$prepareEventLoops()
{
  /* Patch the global object so that our event loop methods are the kind that understand references */
  const loopHnd = require('./event-loop-asyncio').makeLoop();
  const eventLoopMethods =  require('./event-loop');
  for (let name in eventLoopMethods)
    globalThis[name] = eventLoopMethods[name];
  return loopHnd;
}

/**
 * Set the global arguments array, which is just the program's argv.  We use an argvBuilder function to
 * get around PythonMonkey's missing list->Array coercion. /wg june 2023 
 */
exports.makeArgvBuilder = function globalInit$$makeArgvBuilder()
{
  const argv = [];
  globalThis.arguments = argv;
  return argvBuilder;

  function argvBuilder(arg)
  {
    globalThis.arguments.push(arg)
  }
}

/**
 * runProgramModule wants to include the require.cache from the pre-program loads (e.g. via -r or -e), but
 * due to current bugs in PythonMonkey, we can't access the cache property of require because it is a JS
 * function wrapped in a Python function wrapper exposed to script as a native function.
 *
 * This patch swaps in a descended version of require(), which has the same require.cache, but that has
 * side effects in terms of local module id resolution, so this patch happens only right before we want
 * to fire up the program module.
 */
exports.patchGlobalRequire = function pmjs$$patchGlobalRequire()
{
  globalThis.require = require;
}

exports.initReplLibs = function pmjs$$initReplLibs()
{
  globalThis.util = require('util');
}

/**
 * Temporary API until we get EventEmitters working. Replace this export for a custom handler.
 */
exports.uncaughtExceptionHandler = function globalInit$$uncaughtExceptionHandler(error)
{
  console.error(error);
  python.exit(1);
}

/**
 * Temporary API until we get EventEmitters working. Replace this export for a custom handler.
 */
exports.unhandledRejectionHandler = function globalInit$$unhandledRejectionHandler(error)
{
  console.error(error);
  python.exit(1);
}
