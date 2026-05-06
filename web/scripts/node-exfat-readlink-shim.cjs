const fs = require("fs");

const shouldPatch = process.platform === "win32";

function isExfatNonSymlinkReadlinkError(error, targetPath) {
  if (!shouldPatch || error?.code !== "EISDIR" || error?.syscall !== "readlink") {
    return false;
  }

  try {
    return !fs.lstatSync(targetPath).isSymbolicLink();
  } catch {
    return false;
  }
}

function createNonSymlinkReadlinkError(targetPath) {
  // exFAT can report EISDIR for readlink on regular files; tooling expects EINVAL.
  const error = new Error(`EINVAL: invalid argument, readlink '${targetPath}'`);
  error.errno = -4071;
  error.code = "EINVAL";
  error.syscall = "readlink";
  error.path = targetPath;
  return error;
}

function normalizeReadlinkError(error, targetPath) {
  if (isExfatNonSymlinkReadlinkError(error, targetPath)) {
    return createNonSymlinkReadlinkError(targetPath);
  }
  return error;
}

if (shouldPatch) {
  const originalReadlink = fs.readlink;
  const originalReadlinkSync = fs.readlinkSync;
  const originalPromisesReadlink = fs.promises?.readlink;

  fs.readlink = function readlink(path, options, callback) {
    const cb = typeof options === "function" ? options : callback;
    const wrappedCallback = (error, linkString) => {
      cb(error ? normalizeReadlinkError(error, path) : null, linkString);
    };

    if (typeof options === "function") {
      return originalReadlink.call(this, path, wrappedCallback);
    }

    return originalReadlink.call(this, path, options, wrappedCallback);
  };

  fs.readlinkSync = function readlinkSync(path, options) {
    try {
      return originalReadlinkSync.call(this, path, options);
    } catch (error) {
      throw normalizeReadlinkError(error, path);
    }
  };

  if (originalPromisesReadlink) {
    fs.promises.readlink = async function readlink(path, options) {
      try {
        return await originalPromisesReadlink.call(this, path, options);
      } catch (error) {
        throw normalizeReadlinkError(error, path);
      }
    };
  }
}
