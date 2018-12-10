from openmdao.api import ExecComp as OpenmdaoExecComp
import time


class ExecComp(OpenmdaoExecComp):
    """Executable component based on mathematical expression with the additional function of adding a sleep time to
    simulate longer execution times."""

    def __init__(self, exprs, sleep_time=None, **kwargs):
        super(ExecComp, self).__init__(exprs, **kwargs)
        self.sleep_time = sleep_time

    def compute(self, inputs, outputs):
        """
        Execute this component's assignment statements.

        Parameters
        ----------
        inputs : `Vector`
            `Vector` containing inputs.

        outputs : `Vector`
            `Vector` containing outputs.
        """
        OpenmdaoExecComp.compute(self, inputs, outputs)
        if self.sleep_time is not None:
            time.sleep(self.sleep_time)