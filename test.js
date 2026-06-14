const katex = require('katex');

const formula = String.raw`I = \begin{vmatrix} \frac{\partial \varphi}{\partial u} & \frac{\partial \varphi}{\partial v} \\ \frac{\partial \psi}{\partial u} & \frac{\partial \psi}{\partial v} \end{matrix}`;

try {
    console.log("Formula:", formula);
    const result = katex.renderToString(formula);
    console.log("Success");
} catch (e) {
    console.error("Error:", e.message);
}
