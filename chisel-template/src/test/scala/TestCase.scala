import chisel3._
import chisel3.experimental.BundleLiterals._
import chisel3.simulator.EphemeralSimulator._
import org.scalatest.freespec.AnyFreeSpec
import org.scalatest.matchers.must.Matchers

class Mux4to1Tester extends AnyFreeSpec with Matchers {
  "Mux4to1 should select the correct input" in {
    simulate(new Mux4to1) { dut =>
      val inputs = Seq(0xF, 0xF0, 0xF00, 0xF000)
      for (sel <- 0 to 3) {
        dut.io.in0.poke(inputs(0).U)
        dut.io.in1.poke(inputs(1).U)
        dut.io.in2.poke(inputs(2).U)
        dut.io.in3.poke(inputs(3).U)
        dut.io.sel.poke(sel.U)
        dut.clock.step()
        dut.io.out.expect(inputs(sel).U)
      }
    }
  }
}