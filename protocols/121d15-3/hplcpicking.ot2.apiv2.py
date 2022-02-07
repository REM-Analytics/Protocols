# metadata
metadata = {
    'protocolName': 'HPLC Picking',
    'author': 'Nick <protocols@opentrons.com>',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.11'
}


def run(ctx):

    [input_file, default_transfer_vol, p300_mount] = get_values(  # noqa: F821
        'input_file', 'default_transfer_vol', 'p300_mount')

    # load labware
    rack = ctx.load_labware('eurofins_96x2ml_tuberack', '2', 'tuberack')
    plates = [
        ctx.load_labware('irishlifesciences_96_wellplate_2200ul', slot,
                         f'plate {i+1}')
        for i, slot in enumerate(['10', '7', '4', '1'])]
    tips300 = [ctx.load_labware('opentrons_96_tiprack_300ul', '11')]

    # pipette
    p300 = ctx.load_instrument('p300_single_gen2', p300_mount,
                               tip_racks=tips300)

    # parse
    data = [
        line.split(',') for line in input_file.splitlines()[1:]
        if line and line.split(',')[0].strip()]

    # order
    wells_ordered = [
        well for plate in plates for row in plate.rows() for well in row]

    dest_vols = {}
    prev_dest = None
    for i, line in enumerate(data):
        source = wells_ordered[0]
        dest = rack.wells_by_name()[line[1].upper()]
        if len(line) > 2 and line[2]:
            vol = round(float(line[2]))
        else:
            vol = default_transfer_vol

        # check for volumes slightly over 300ul from HPLC input files
        vol = 300 if 300 < vol < 305 else vol

        if dest != prev_dest:
            if p300.has_tip:
                p300.drop_tip()
            p300.pick_up_tip()
        p300.transfer(vol, source.bottom(0.5), dest.top(-1), new_tip='never')
        prev_dest = dest

        # track volumes for final adjustment
        if dest not in dest_vols:
            dest_vols[dest] = vol
        else:
            dest_vols[dest] += vol
    p300.drop_tip()

    # final adjustment with water up to 1500ul
    ctx.pause('Replace plate 4 in slot 1 with water reservoir. Resume once \
finished.')
    water = plates[-1].wells_by_name()['D4'].bottom(1)
    p300.pick_up_tip()
    for tube, vol in dest_vols.items():
        adjustment = 1500 - vol
        if adjustment > 0:
            p300.transfer(adjustment, water, tube.top(-1), new_tip='never')
    p300.drop_tip()
