const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("asculto", {
  modelsStatus: () => ipcRenderer.invoke("models:status"),
  infer: (head, mel) => ipcRenderer.invoke("infer", { head, mel }),
});
