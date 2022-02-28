import math
from opentrons.protocol_api.labware import OutOfTipsError
from opentrons import types

metadata = {
    'protocolName': '''ArcBio RNA Workflow Continuous:
    Pre-PCR Instrument: Part-4: cDNA Library Purification, Ligation''',
    'author': 'Steve Plonk <protocols@opentrons.com>',
    'apiLevel': '2.11'
}


def run(ctx):

    # get parameter values from json above
    [count_samples, clearance_reservoir, height_engage, time_engage, offset_x,
     time_dry] = get_values(  # noqa: F821
      'count_samples', 'clearance_reservoir', 'height_engage', 'time_engage',
      'offset_x', 'time_dry')

    ctx.set_rail_lights(True)

    if not 1 <= count_samples <= 96:
        raise Exception('Invalid sample count (must be 1-96).')

    num_cols = math.ceil(count_samples / 8)

    # helper functions

    # pause, flash lights, notify user
    def pause_attention(message):
        ctx.set_rail_lights(False)
        ctx.delay(seconds=5)
        ctx.set_rail_lights(True)
        ctx.delay(seconds=5)
        ctx.set_rail_lights(False)
        ctx.pause(message)

    # notify user to replenish tips
    def pick_up_or_refill(pip, vol=200):
        nonlocal tipCtr
        try:
            if vol == 200:
                pip.pick_up_tip()
            else:
                if tipCtr < len(tips300.rows()[0]):
                    pip.pick_up_tip(tips300.rows()[0][tipCtr])
                    tipCtr += 1
                else:
                    tipCtr = 0
                    pause_attention(
                     """Please Refill the 300 uL Tip Box
                     and Empty the Tip Waste""")
                    pip.pick_up_tip(tips300.rows()[0][tipCtr])
                    tipCtr += 1
        except OutOfTipsError:
            pause_attention(
             """Please Refill the {} Tip Boxes
             and Empty the Tip Waste""".format(pip))
            pip.reset_tipracks()
            pip.pick_up_tip()

    # set liquid volume
    def liq_volume(wells, vol):
        for well in wells:
            well.liq_vol = vol

    # return liquid height in a well
    def liq_height(well):
        if well.diameter is not None:
            radius = well.diameter / 2
            cse = math.pi*(radius**2)
        elif well.length is not None:
            cse = well.length*well.width
        else:
            cse = None
        if cse:
            return well.liq_vol / cse
        else:
            raise Exception("""Labware definition must
                supply well radius or well length and width.""")

    # apply 10 mm/sec limit when tip leaves liquid
    def slow_tip_withdrawal(current_pipette, well_location):
        if current_pipette.mount == 'right':
            axis = 'A'
        else:
            axis = 'Z'
        ctx.max_speeds[axis] = 10
        current_pipette.move_to(well_location.top())
        ctx.max_speeds[axis] = None

    # tips, p20 multi, p300 multi
    tips20 = [ctx.load_labware(
     "opentrons_96_filtertiprack_20ul", str(slot)) for slot in [10, 11]]
    p20m = ctx.load_instrument(
        "p20_multi_gen2", 'left', tip_racks=tips20)
    tips200 = [
     ctx.load_labware(
      "opentrons_96_filtertiprack_200ul", str(slot)) for slot in [7, 8]]
    tips300 = ctx.load_labware("opentrons_96_tiprack_300ul", 9)
    tipCtr = 0
    p300m = ctx.load_instrument(
        "p300_multi_gen2", 'right', tip_racks=tips200)

    # reagents block for index plate, enzyme 16 plate
    reagents = ctx.load_labware(
     'opentrons_96_aluminumblock_biorad_wellplate_200ul', '2', 'Reagents')

    # reservoir for beads and tris
    reservoir = ctx.load_labware('nest_12_reservoir_15ml', '5', 'Reservoir')
    [beads, tris] = [reservoir.wells()[index] for index in [0, -1]]

    # reservoirs for 80 pct etoh and waste
    [waste, etoh] = [
     ctx.load_labware('nest_1_reservoir_195ml', str(
      slot), name).wells()[0] for slot, name in zip(
      [4, 6], ['waste', '80 percent etoh'])]
    liq_volume([etoh], 48000)

    # input samples
    temp = ctx.load_module('temperature module gen2', '3')
    sampleplate200 = temp.load_labware(
     'eppendorftwin.tec96_96_aluminumblock_200ul',
     "Sample Plate at 4 Degrees")
    temp.set_temperature(4)

    # magnetic module with 200 uL PCR plate
    mag = ctx.load_module('magnetic module gen2', '1')
    mag.disengage()
    mag_plate = mag.load_labware(
     'eppendorf_96_wellplate_200ul', 'Mag Plate')

    ctx.comment("STEP - KAPA Pure Beads")

    for column in mag_plate.columns()[:num_cols]:
        p300m.pick_up_tip()
        p300m.aspirate(65.2, beads.bottom(clearance_reservoir), rate=0.5)
        ctx.delay(seconds=1)
        p300m.dispense(65.2, column[0])
        p300m.mix(10, 92)
        p300m.drop_tip()

    ctx.delay(minutes=10)
    mag.engage(height_from_base=height_engage)
    ctx.delay(minutes=time_engage)

    # remove supernatant
    for index, column in enumerate(mag_plate.columns()[:num_cols]):
        p300m.pick_up_tip()
        p300m.aspirate(115.2, column[0].bottom(4), rate=0.33)
        p300m.aspirate(
         50, column[0].bottom(1).move(types.Point(
          x={True: 1}.get(not index % 2, -1)*offset_x, y=0, z=0)), rate=0.33)
        p300m.dispense(165.2, waste.top())
        p300m.blow_out()
        p300m.drop_tip()

    for repeat in range(2):
        # add ethanol
        pick_up_or_refill(p300m, 300)
        for column in mag_plate.columns()[:num_cols]:
            etoh.liq_vol -= 1520
            p300m.aspirate(190, etoh.bottom(liq_height(etoh)-3))
            p300m.air_gap(10)
            p300m.dispense(200, column[0].top())
            ctx.delay(seconds=0.5)
            p300m.blow_out()
        p300m.drop_tip()

        ctx.delay(seconds=30)

        # remove sup
        for column in mag_plate.columns()[:num_cols]:
            pick_up_or_refill(p300m)
            p300m.aspirate(110, column[0].bottom(4), rate=0.5)
            p300m.aspirate(
             80, column[0].bottom(1).move(types.Point(x={True: 1}.get(
              not index % 2, -1)*offset_x, y=0, z=0)), rate=0.5)
            p300m.air_gap(10)
            p300m.dispense(200, waste.top())
            ctx.delay(seconds=0.5)
            p300m.blow_out()
            p300m.drop_tip()

    mag.disengage()

    # air dry bead pellets
    ctx.delay(minutes=time_dry)

    # resuspend bead pellet in Tris
    for index, column in enumerate(mag_plate.columns()[:num_cols]):
        p20m.pick_up_tip()
        p20m.aspirate(17, tris.bottom(clearance_reservoir))
        p20m.dispense(
         17, column[0].bottom(1).move(types.Point(
          x={True: -1}.get(not index % 2, 1)*offset_x, y=0, z=0)))
        p20m.mix(10, 13.6)
        p20m.drop_tip()

    ctx.delay(minutes=2)

    mag.engage(height_from_base=height_engage)
    ctx.delay(minutes=time_engage)

    pause_attention(
     '''Place a fresh 200 uL PCR plate on the temperature module.
     Place the index plate on the reagents block in slot 2. Resume.''')

    # combine 10 uL index and eluted sample
    for i, column in enumerate(sampleplate200.columns()[:num_cols]):
        pick_up_or_refill(p20m)
        p20m.transfer(10, reagents.columns()[i][0], column[0], new_tip='never')
        p20m.drop_tip()

    for index, column in enumerate(mag_plate.columns()[:num_cols]):
        pick_up_or_refill(p20m)
        p20m.transfer(
         15, column[0].bottom().move(types.Point(
          x={True: 1}.get(not index % 2, -1)*offset_x, y=0, z=0)),
         sampleplate200.columns()[index][0],
         mix_after=(2, 15), new_tip='never')
        p20m.drop_tip()

    ctx.comment("STEP - Ligation")

    pause_attention(
     '''Place the enzyme 16 plate on the reagents block in slot 2. Resume.''')

    for index, column in enumerate(sampleplate200.columns()[:num_cols]):
        pick_up_or_refill(p300m)
        source = reagents.columns()[index][0]
        p300m.aspirate(25, source, rate=0.5)
        ctx.delay(seconds=1)
        slow_tip_withdrawal(p300m, source)
        p300m.dispense(25, column[0], rate=0.5)
        ctx.delay(seconds=1)
        p300m.mix(10, 40)
        p300m.drop_tip()

    pause_attention(
     '''cDNA Library Purification, Ligation protocol complete.
     Proceed to off deck cycler steps and then the post PCR OT-2 protocols.''')
