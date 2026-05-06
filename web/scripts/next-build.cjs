const path = require("path");

const shimPath = path.join(__dirname, "node-exfat-readlink-shim.cjs");
const requireShimOption = `--require=${shimPath}`;

if (!process.env.NODE_OPTIONS?.includes(requireShimOption)) {
  process.env.NODE_OPTIONS = [process.env.NODE_OPTIONS, requireShimOption].filter(Boolean).join(" ");
}

require(shimPath);

process.argv = [process.execPath, "next", "build", ...process.argv.slice(2)];
require("next/dist/bin/next");
