OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS
{
  boot PT_LOAD FLAGS(5);
  code PT_LOAD FLAGS(5);
  data PT_LOAD FLAGS(6);
}
SECTIONS
{
  . = 0;
  .boot : { KEEP(*(.text.start)) } :boot
  ASSERT(. <= 0x200, "startup overlaps result signature")
  . = 0x1000;
  .text : { *(.text .text.*) } :code
  .rodata : { *(.rodata .rodata.*) } :code
  .data : { *(.data .data.*) *(.sdata .sdata.*) } :data
  . = ALIGN(8);
  __bss_start = .;
  .bss (NOLOAD) : { *(.bss .bss.*) *(.sbss .sbss.*) *(COMMON) } :data
  . = ALIGN(8);
  __bss_end = .;
  ASSERT(. < 0xd000, "image overlaps reserved stack")
  __stack_top = 0xf000;
  /DISCARD/ : { *(.comment) *(.eh_frame*) }
}
