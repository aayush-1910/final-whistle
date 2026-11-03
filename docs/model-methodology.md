# Model Methodology

> Describes the Elo, Poisson, and Monte Carlo models used by Final Whistle.
> This document will be expanded as models are implemented and validated.

## Overview

V1 uses three layers:

1. **Elo rating** — estimates relative team strength from historical results.
2. **Poisson goal model** — estimates expected goals and match outcome probabilities.
3. **Monte Carlo simulation** — samples remaining-season outcomes to produce
   title, position, qualification, relegation, and advancement probabilities.

Details, parameters, and validation results will be added during
Milestones 3–6.

