
#include "include/internalBinding.hh"
#include "include/pyTypeFactory.hh"
#include "include/PyEventLoop.hh"

#include <jsapi.h>

static bool enqueueWithDelay(JSContext *cx, unsigned argc, JS::Value *vp) {
  JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
  JS::HandleValue jobArgVal = args.get(0);
  double delaySeconds = args.get(1).toNumber();

  // Convert to a Python function
  // FIXME (Tom Tang): memory leak, not free-ed
  JS::RootedObject *thisv = new JS::RootedObject(cx, nullptr);
  JS::RootedValue *jobArg = new JS::RootedValue(cx, jobArgVal);
  PyObject *job = pyTypeFactory(cx, thisv, jobArg)->getPyObject();

  // Schedule job to the running Python event-loop
  PyEventLoop loop = PyEventLoop::getRunningLoop();
  if (!loop.initialized()) return false;
  PyEventLoop::AsyncHandle handle = loop.enqueueWithDelay(job, delaySeconds);

  // Return the `timeoutID` to use in `clearTimeout`
  args.rval().setDouble((double)PyEventLoop::AsyncHandle::getUniqueId(std::move(handle)));
  return true;
}

// TODO (Tom Tang): move argument checks to the JavaScript side
static bool cancelByTimeoutId(JSContext *cx, unsigned argc, JS::Value *vp) {
  using AsyncHandle = PyEventLoop::AsyncHandle;
  JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
  JS::HandleValue timeoutIdArg = args.get(0);

  args.rval().setUndefined();

  // silently does nothing when an invalid timeoutID is passed in
  if (!timeoutIdArg.isInt32()) {
    return true;
  }

  // Retrieve the AsyncHandle by `timeoutID`
  int32_t timeoutID = timeoutIdArg.toInt32();
  AsyncHandle *handle = AsyncHandle::fromId((uint32_t)timeoutID);
  if (!handle) return true; // does nothing on invalid timeoutID

  // Cancel this job on Python event-loop
  handle->cancel();

  return true;
}

static JSFunctionSpec internalBindingTimers[] = {
  JS_FN("enqueueWithDelay", enqueueWithDelay, /* nargs */ 2, 0),
  JS_FN("cancelByTimeoutId", cancelByTimeoutId, 1, 0),
  JS_FS_END
};

JSObject *createTimersInternalBinding(JSContext *cx) {
  JS::RootedObject timers(cx, JS_NewObjectWithGivenProto(cx, nullptr, nullptr)); // timers = Object.create(null)
  if (!JS_DefineFunctions(cx, timers, internalBindingTimers)) { return nullptr; }
  return timers;
}
