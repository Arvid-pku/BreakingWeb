import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import "@breakingweb/shared/styles/base.css";

import { App } from "./App";
import "./reddit.css";

const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <BrowserRouter basename={basename}>
    <App />
  </BrowserRouter>,
);
