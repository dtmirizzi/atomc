import React from "react";
import ReactDOM from "react-dom/client";
import { StudioApp } from "./studio-app.js";
import "./styles.css";

const root = document.getElementById("root");

if (!root) throw new Error('Studio root element "#root" is missing from the document.');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <StudioApp />
  </React.StrictMode>,
);
