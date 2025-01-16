import chisel3._
import chisel3.experimental.BundleLiterals._
import chisel3.simulator.EphemeralSimulator._
import org.scalatest.freespec.AnyFreeSpec
import org.scalatest.matchers.must.Matchers

class CounterTester extends AnyFreeSpec with Matchers {
  "Counter should count correctly and wrap around" in {
    simulate(new Counter(4)) { dut =>
      dut.io.enable.poke(true.B)
      dut.io.reset.poke(true.B)
      dut.clock.step()
      dut.io.reset.poke(false.B)
      for (i <- 0 until 16) {
        dut.io.count.expect(i.U)
        dut.clock.step()
      }
      dut.io.count.expect(0.U) // Wrap around
    }
  }
}