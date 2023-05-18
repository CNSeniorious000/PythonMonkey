
#include "include/internalBinding.hh"
#include "include/pyTypeFactory.hh"

#include <jsapi.h>
#include <js/String.h>
#include <Python.h>

// TODO (Tom Tang): figure out a better way to register InternalBindings to namespace
JSObject *getInternalBindingsByNamespace(JSContext *cx, JSLinearString *namespaceStr) {
  if (JS_LinearStringEqualsLiteral(namespaceStr, "timers")) {
    return createTimersInternalBinding(cx);
  } else { // not found
    return nullptr;
  }
}

/**
 * @brief Implement the `internalBinding(namespace)` function
 */
static bool internalBindingFn(JSContext *cx, unsigned argc, JS::Value *vp) {
  JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
  JS::AutoCheckCannotGC autoNoGC(cx);

  // Get the `namespace` argument as string
  JS::HandleValue namespaceStrArg = args.get(0);
  JSLinearString *namespaceStr = JS_EnsureLinearString(cx, namespaceStrArg.toString());

  args.rval().setObjectOrNull(getInternalBindingsByNamespace(cx, namespaceStr));
  return true;
}

/**
 * @brief Convert the `internalBinding(namespace)` function to a Python function
 */
// TODO (Tom Tang): refactor once we get object coercion support
PyObject *getInternalBindingPyFn(JSContext *cx) {
  // Create the JS `internalBinding` function
  JSObject *jsFn = (JSObject *)JS_NewFunction(cx, internalBindingFn, 1, 0, "internalBinding");

  // Convert to a Python function
  // FIXME (Tom Tang): memory leak, not free-ed
  JS::RootedObject *thisObj = new JS::RootedObject(cx, nullptr);
  JS::RootedValue *jsFnVal = new JS::RootedValue(cx, JS::ObjectValue(*jsFn));
  PyObject *pyFn = pyTypeFactory(cx, thisObj, jsFnVal)->getPyObject();

  return pyFn;
}

