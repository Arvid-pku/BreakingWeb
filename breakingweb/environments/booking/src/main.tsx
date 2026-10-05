import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@breakingweb/shared/styles/base.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename="/env/booking">
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
