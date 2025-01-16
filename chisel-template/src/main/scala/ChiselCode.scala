import chisel3._

class Counter(val n: Int) extends Module {
  val io = IO(new Bundle {
    val reset = Input(Bool())
    val enable = Input(Bool())
    val count = Output(UInt(n.W))
  })

  // Your implementation here
}