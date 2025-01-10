import chisel3._

class Mux4to1 extends Module {
  val io = IO(new Bundle {
    val in0 = Input(UInt(16.W))
    val in1 = Input(UInt(16.W))
    val in2 = Input(UInt(16.W))
    val in3 = Input(UInt(16.W))
    val sel = Input(UInt(2.W))
    val out = Output(UInt(16.W))
  })

  // Your implementation here
  io.out := 2.U
}