/// <reference types="vite/client" />

declare module "virtual:guard-data" {
  const dataset: import("./lib/types").Dataset;
  export default dataset;
}
